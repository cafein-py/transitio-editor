"""The editor's HTTP API over a transitio FeedEditor."""

from __future__ import annotations

import math
import os
import re

# shared with the catalogue's per-feed mode summary
from transitio_editor._registry import base_route_type as _base_route_type


def _geojson_feature(geometry_mapping, properties):
    return {"type": "Feature", "geometry": geometry_mapping, "properties": properties}


def _json_value(value):
    """Coerce a GeoDataFrame cell to a JSON-serializable value, or ``None``."""
    if isinstance(value, float) and math.isnan(value):
        return None
    if isinstance(value, list):
        return [item.item() if hasattr(item, "item") else item for item in value]
    if hasattr(value, "item"):  # numpy scalar
        return value.item()
    return value


def _write_sidecar(path, text):
    """Write a provenance sidecar atomically via a unique temp + rename.

    ``mkstemp`` creates an unpredictably named file with exclusive-create
    semantics in the target directory (so no pre-planted symlink or hard
    link is followed), then ``os.replace`` atomically moves it onto the
    destination, replacing any symlink there without following it.
    """
    import tempfile

    directory = os.path.dirname(path) or "."
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=".prov-", suffix=".part")
    try:
        with os.fdopen(fd, "w") as handle:
            handle.write(text)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _clean_id(value):
    # id columns in real feeds occasionally carry stray whitespace
    return str(value).strip() if value is not None else ""


def _has_geometry(value):
    """Whether a row's geometry cell holds a real geometry.

    A feed can carry a stop without coordinates or a shape with a single
    point, which become missing geometries — read back from ``iterrows``
    as ``None`` or as NaN, depending on the pandas/geopandas versions.
    """
    return hasattr(value, "__geo_interface__")


def _merge_prefixes(names, feed_ids):
    """Id prefixes for a merge, derived from the feeds' display names.

    transitio requires unique, non-empty, colon-free prefixes; names are
    stripped of colons and deduplicated, falling back to the feed id.
    """
    prefixes = []
    used = set()
    for name, feed_id in zip(names, feed_ids):
        prefix = str(name).replace(":", "").strip() or feed_id
        candidate = prefix
        suffix = 2
        while candidate in used:
            candidate = f"{prefix}-{suffix}"
            suffix += 1
        used.add(candidate)
        prefixes.append(candidate)
    return prefixes


def _json_safe_name(name):
    """Whether a filesystem name survives JSON encoding.

    POSIX names need not be UTF-8; such a name would fail the response
    encoding and take the whole listing down with it.
    """
    try:
        name.encode("utf-8")
    except UnicodeEncodeError:
        return False
    return True


# Windows refuses these as file basenames, whatever the extension.
_RESERVED_NAMES = frozenset(
    ["CON", "PRN", "AUX", "NUL"]
    + [f"COM{digit}" for digit in range(1, 10)]
    + [f"LPT{digit}" for digit in range(1, 10)]
)


def _group_name(value):
    """A usable group name from a request field, or None."""
    if not isinstance(value, str):
        return None
    name = value.strip()
    if not name or len(name) > 60:
        return None
    # a lone surrogate would break the JSON response — and every later
    # catalogue response, once stored
    return name if _json_safe_name(name) else None


def _finite_number(value):
    """A finite float from a JSON number, or None (bools are not numbers)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    try:
        number = float(value)
    except (OverflowError, ValueError):  # an int beyond the float range
        return None
    return number if math.isfinite(number) else None


def _crop_ring(ring):
    """Whether a ring is a usable WGS84 boundary."""
    if not isinstance(ring, list) or len(ring) < 3:
        return False
    points = []
    for point in ring:
        if not isinstance(point, (list, tuple)) or len(point) != 2:
            return False
        lon, lat = (_finite_number(value) for value in point)
        if lon is None or lat is None:
            return False
        if not -180 <= lon <= 180 or not -90 <= lat <= 90:
            return False
        points.append((lon, lat))
    # Compare the distinct points, in order: a repeated vertex (an extra
    # click on the same spot, or a ring closed by hand) must not decide
    # the outcome.
    distinct = list(dict.fromkeys(points))
    if len(distinct) < 3:
        return False
    # A ring whose points all lie on one line encloses nothing, so
    # cropping to it would silently produce empty feeds. Anything else is
    # left to transitio's even-odd test, which is defined for any ring —
    # a signed area would cancel to zero for a self-intersecting one and
    # reject it wrongly.
    (x0, y0), (x1, y1) = distinct[0], distinct[1]
    return any(
        abs((x1 - x0) * (y - y0) - (y1 - y0) * (x - x0)) > 0 for x, y in distinct[2:]
    )


def _crop_area(shape):
    """The AOI a crop request describes, or None when it is malformed.

    Either a GeoJSON Polygon/MultiPolygon mapping (cropped polygon-true
    by transitio) or a ``[minx, miny, maxx, maxy]`` box. Checked here in
    full, so a shape that cannot bound an area is a request error rather
    than a per-feed failure.
    """
    if isinstance(shape, dict):
        kind = shape.get("type")
        coordinates = shape.get("coordinates")
        if not isinstance(coordinates, list) or not coordinates:
            return None
        parts = [coordinates] if kind == "Polygon" else coordinates
        if kind not in ("Polygon", "MultiPolygon"):
            return None
        for rings in parts:
            if not isinstance(rings, list) or not rings:
                return None
            if not all(_crop_ring(ring) for ring in rings):
                return None
        return shape
    if isinstance(shape, (list, tuple)) and len(shape) == 4:
        box = tuple(_finite_number(value) for value in shape)
        if any(value is None for value in box):
            return None
        minx, miny, maxx, maxy = box
        if minx >= maxx or miny >= maxy:
            return None
        if not (-180 <= minx and maxx <= 180 and -90 <= miny and maxy <= 90):
            return None
        return box
    return None


def _geocode_bounds(query):
    """The WGS84 bounds of a geocoded place name.

    Nominatim via pyrosm — the same geocoder the OSM acquire flow uses,
    so "Helsinki" means the same thing in both.
    """
    from transitio.osm._fetch import _as_geometry

    return _as_geometry(query).bounds


def _padded_span(low, high, minimum, bound_low, bound_high):
    """``[low, high]`` widened to ``minimum``, shifted to stay in bounds.

    Shifting (rather than clamping the padded edges) keeps the minimum
    extent even for a place sitting on a WGS84 boundary.
    """
    if high - low < minimum:
        pad = (minimum - (high - low)) / 2
        low -= pad
        high += pad
    if low < bound_low:
        high += bound_low - low
        low = bound_low
    if high > bound_high:
        low -= high - bound_high
        high = bound_high
    return max(bound_low, low), high


def _place_bbox(query):
    """A searchable bounding box for a place name.

    A place that geocodes to a point (or a sliver) is padded to a
    minimal extent, so a bbox-overlap feed search has an area to work
    with instead of a zero-area box nothing overlaps.
    """
    minx, miny, maxx, maxy = _geocode_bounds(query)
    minx, maxx = _padded_span(minx, maxx, 0.1, -180.0, 180.0)
    miny, maxy = _padded_span(miny, maxy, 0.05, -90.0, 90.0)
    return (minx, miny, maxx, maxy)


def _sha256_file(path):
    """The streamed SHA-256 hex digest of a file."""
    import hashlib

    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _feed_filename(name):
    """A safe ``.zip`` filename from a feed's display name."""
    stem = re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip("-.")[:60]
    if not stem:
        stem = "merged"
    elif stem.split(".")[0].upper() in _RESERVED_NAMES:
        stem = f"feed-{stem}"
    return f"{stem}.zip"


def _editor_from_tables(tables):
    """A FeedEditor over already-merged tables, with no source file.

    transitio has no public constructor from tables, and writing the
    merged feed out just to read it back would cost a validation pass
    the user has not asked for yet; the entry is validated on save like
    any other feed.
    """
    from transitio.edit import FeedBuilder, FeedEditor

    editor = FeedEditor.__new__(FeedEditor)
    FeedBuilder.__init__(editor)
    editor.source = None
    editor.tables = tables
    return editor


def _shape_route_types(editor):
    """Map each shape_id to its route's base route_type via the trips table.

    A shape shared by several routes takes the first trip's route.
    """
    tables = getattr(editor, "tables", {})
    trips = tables.get("trips.txt")
    routes = tables.get("routes.txt")
    if trips is None or routes is None:
        return {}
    if {"shape_id", "route_id"} - set(trips.columns):
        return {}
    if {"route_id", "route_type"} - set(routes.columns):
        return {}
    route_types = {
        _clean_id(route_id): route_type
        for route_id, route_type in zip(routes["route_id"], routes["route_type"])
    }
    mapping = {}
    for route_id, shape_id in zip(trips["route_id"], trips["shape_id"]):
        shape_id = _clean_id(shape_id)
        if not shape_id or shape_id in mapping:
            continue
        base = _base_route_type(route_types.get(_clean_id(route_id)))
        if base is not None:
            mapping[shape_id] = base
    return mapping


def _network_features(frame):
    """A GeoJSON FeatureCollection of an OsmEditor nodes/ways frame."""
    geometry_name = frame.geometry.name
    features = []
    for _, row in frame.iterrows():
        geometry = row[geometry_name]
        if not _has_geometry(geometry):
            continue
        properties = {}
        for key, value in row.items():
            if key == geometry_name:
                continue
            clean = _json_value(value)
            if clean is not None:
                properties[key] = clean
        features.append(_geojson_feature(geometry.__geo_interface__, properties))
    return {"type": "FeatureCollection", "features": features}


def create_app(
    editor=None,
    *,
    osm_pbf=None,
    network_type="driving",
    snap_custom_filter=None,
    network_filter=None,
    max_network_ways=200000,
    allowed_hosts=None,
    catalog_factory=None,
):
    """Build the FastAPI app serving a registry of loaded feeds.

    The app exposes the feed's tables and geometries, mutation endpoints
    mirroring the editor helpers, a snapping endpoint backed by
    :func:`~transitio.edit.snap_to_network` (when ``osm_pbf`` is given),
    and a save endpoint running the validator. It serves everything on
    the loopback interface for a single local user; there is no
    authentication.

    Parameters
    ----------
    editor : FeedEditor or FeedBuilder, optional
        The first feed loaded into the catalogue (the CLI's opened
        feed). More feeds are added through the catalogue endpoints;
        mutations target the current feed, display aggregates the active
        feeds.
    osm_pbf : str or pathlib.Path, optional
        Initial OSM extract enabling the network endpoints and ``POST
        /api/shapes/snap`` (requires the ``transitio[snap]`` extra). An
        extract can also be acquired at runtime via ``POST
        /api/osm/download``, which replaces the current source.
    network_type : str, default "driving"
        pyrosm network type for snapping.
    snap_custom_filter : dict, optional
        Default pyrosm Overpass-style tag filter for snapping (e.g.
        ``{"railway": ["tram"]}``); a per-request ``custom_filter``
        overrides it. See :func:`~transitio.edit.snap_to_network`.
    network_filter : dict, optional
        pyrosm Overpass-style tag filter selecting the editable OSM
        network served at ``GET /api/network/*`` (from ``osm_pbf``);
        defaults to all highways plus tram/rail/light_rail/subway. See
        :class:`~transitio.edit.OsmEditor`.
    max_network_ways : int, default 200000
        Refuse to serve an OSM network with more ways than this (guards
        the browser); ``0`` disables the cap.
    allowed_hosts : list of str, optional
        Accepted ``Host`` header values (DNS-rebinding guard); defaults
        to the loopback names.
    catalog_factory : callable, optional
        Zero-argument factory returning a
        :class:`~transitio.catalog.MobilityDatabase` for ``GET
        /api/search``; defaults to constructing one lazily (token from
        the environment, else the CSV fallback). Mainly a test seam.

    Returns
    -------
    fastapi.FastAPI
    """
    try:
        from fastapi import Body, FastAPI, HTTPException
        from fastapi.responses import HTMLResponse
    except ImportError as error:
        raise ImportError(
            "the editor requires fastapi and uvicorn; reinstall transitio-editor"
        ) from error

    from transitio.exceptions import InvalidFeedError

    import threading

    from starlette.middleware.trustedhost import TrustedHostMiddleware

    # The Swagger page would pull its assets from a CDN into this origin;
    # the app stays CDN-free, and the schema remains at /openapi.json.
    app = FastAPI(title="transitio editor", docs_url=None, redoc_url=None)
    # A malicious page cannot read loopback responses, but DNS rebinding
    # would let it send requests; pinning the Host header closes that.
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=list(
            # "testserver" is Starlette's test client; not publicly routable.
            allowed_hosts
            or ["127.0.0.1", "localhost", "[::1]", "testserver"]
        ),
    )

    # Cross-origin "simple" POSTs carry the target's Host header, so the
    # trusted-host guard alone does not stop CSRF; state-changing requests
    # from a foreign Origin are refused instead.
    @app.middleware("http")
    async def reject_foreign_origins(request, call_next):
        if request.method in ("POST", "PATCH", "PUT", "DELETE"):
            origin = request.headers.get("origin")
            if origin:
                from urllib.parse import urlsplit

                # Same-origin only: pages on OTHER localhost ports are
                # foreign too; the Host header names this server's origin.
                origin_netloc = urlsplit(origin).netloc
                if origin_netloc != request.headers.get("host", ""):
                    from fastapi.responses import JSONResponse

                    return JSONResponse(
                        {"detail": "cross-origin requests are not allowed"},
                        status_code=403,
                    )
        return await call_next(request)

    # FastAPI runs sync handlers in a threadpool; one lock serializes
    # every touch of the shared current_editor().
    lock = threading.Lock()

    from transitio_editor._registry import FeedRegistry, default_name, entry_dict

    registry = FeedRegistry()
    if editor is not None:
        source = getattr(editor, "source", None)
        registry.add(
            editor,
            default_name(editor),
            source=os.fspath(source) if source else None,
        )

    def _prepared_directory(value, what):
        """Expand and create a caller-supplied output directory."""
        if not isinstance(value, str) or not value.strip():
            raise HTTPException(422, "'directory' must be a non-empty string")
        try:
            directory = Path(value).expanduser()
            directory.mkdir(parents=True, exist_ok=True)
        except (OSError, RuntimeError, ValueError, KeyError) as error:
            raise HTTPException(422, f"cannot use {what}: {error}") from None
        return directory

    def current_editor():
        entry = registry.current_entry()
        if entry is None:
            raise HTTPException(409, "no feed loaded")
        return entry.editor

    # The Mobility Database client is built once, on first search, so the
    # editor starts without touching the network or the catalogue export.
    catalog = {"client": None}
    # Feed objects from searches, keyed by id, so a download can reuse the
    # catalogue entry's hosted-dataset url (works in the CSV mode too).
    search_cache = {}

    def get_catalog():
        if catalog["client"] is None:
            if catalog_factory is not None:
                catalog["client"] = catalog_factory()
            else:
                from transitio.catalog import MobilityDatabase

                catalog["client"] = MobilityDatabase()
        return catalog["client"]

    # The OSM network is loaded once, on first /api/network access, from the
    # current source extract (seeded by --osm-pbf, replaceable at runtime by an
    # AOI download). The same source backs snapping.
    osm_state = {
        "editor": None,
        "source": os.fspath(osm_pbf) if osm_pbf is not None else None,
        "dirty": False,  # unsaved network edits since the last save/load
    }

    def _load_network(source):
        """Load an OsmEditor from a source, enforcing the way-count guard."""
        from transitio.edit import OsmEditor

        try:
            loaded = OsmEditor(os.fspath(source), custom_filter=network_filter)
        except Exception as error:  # noqa: B902
            raise HTTPException(422, f"cannot load OSM network: {error}") from None
        way_count = len(loaded.ways)
        if max_network_ways and way_count > max_network_ways:
            raise HTTPException(
                413,
                f"OSM network has {way_count} ways, over the "
                f"{max_network_ways} limit (use a smaller area, or raise "
                "--max-network-ways)",
            )
        return loaded

    def get_osm_editor():
        if osm_state["source"] is None:
            raise HTTPException(
                409,
                "no OSM network loaded (start with --osm-pbf or acquire one via "
                "POST /api/osm/download)",
            )
        if osm_state["editor"] is None:
            osm_state["editor"] = _load_network(osm_state["source"])
        return osm_state["editor"]

    def _finite(value, field):
        try:
            number = float(value)
        except OverflowError:
            raise ValueError(f"{field} is out of range") from None
        if not math.isfinite(number):
            raise ValueError(f"{field} must be finite")
        return number

    from pathlib import Path

    from fastapi.staticfiles import StaticFiles

    static_dir = Path(__file__).parent / "static"
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

    @app.get("/", response_class=HTMLResponse)
    def index():
        return (static_dir / "index.html").read_text(encoding="utf-8")

    def _history_editor(payload):
        # the caller names the feed its label came from, so a feed switch
        # racing the request cannot make it act on a different feed
        feed_id = payload.get("feed_id")
        if feed_id is not None and feed_id != registry.current:
            raise HTTPException(409, "the current feed changed; refresh first")
        return current_editor()

    @app.post("/api/undo")
    def undo_current(payload: dict = Body(default={})):
        from transitio.exceptions import ChangeLogDesyncError

        with lock:
            editor = _history_editor(payload)
            try:
                label = editor.undo()
            except ChangeLogDesyncError as error:
                raise HTTPException(409, str(error)) from None
            if label is None:
                raise HTTPException(409, "nothing to undo")
            return {
                "undone": label,
                "undo": editor.undo_label,
                "redo": editor.redo_label,
            }

    @app.post("/api/redo")
    def redo_current(payload: dict = Body(default={})):
        from transitio.exceptions import ChangeLogDesyncError

        with lock:
            editor = _history_editor(payload)
            try:
                label = editor.redo()
            except ChangeLogDesyncError as error:
                raise HTTPException(409, str(error)) from None
            if label is None:
                raise HTTPException(409, "nothing to redo")
            return {
                "redone": label,
                "undo": editor.undo_label,
                "redo": editor.redo_label,
            }

    @app.get("/api/feed")
    def feed_summary():
        with lock:
            return _feed_summary()

    def _feed_summary():
        entry = registry.current_entry()
        if entry is None:
            return {
                "source": None,
                "snapAvailable": osm_state["source"] is not None,
                "tables": {},
                "currentFeedId": None,
                "undo": None,
                "redo": None,
            }
        return {
            "source": entry.source,
            "snapAvailable": osm_state["source"] is not None,
            "tables": {
                name: len(table) for name, table in sorted(entry.editor.tables.items())
            },
            "currentFeedId": entry.feed_id,
            # what the next undo/redo would act on, for the GUI's buttons
            "undo": entry.editor.undo_label,
            "redo": entry.editor.redo_label,
        }

    @app.get("/api/tables/{name}")
    def table(name: str, offset: int = 0, limit: int = 1000, q: str | None = None):
        with lock:
            return _table(name, offset, limit, q)

    def _table(name, offset, limit, q=None):
        if name not in current_editor().tables:
            raise HTTPException(404, f"no table {name}")
        frame = current_editor().tables[name]
        needle = (q or "").strip().lower()
        if needle:
            # case-insensitive substring match across every column
            mask = frame.apply(
                lambda column: column.astype(str)
                .str.lower()
                .str.contains(needle, regex=False)
            ).any(axis=1)
            frame = frame[mask]
        window = frame.iloc[offset : offset + max(0, min(limit, 10_000))]
        return {
            "name": name,
            "total": len(frame),
            "offset": offset,
            "columns": list(frame.columns),
            "rows": window.to_dict(orient="records"),
        }

    @app.get("/api/stops")
    def stops_geojson():
        with lock:
            return _stops_geojson()

    def _stops_geojson():
        features = []
        for entry in registry.active_entries():
            try:
                frame = entry.editor.stops
            except ValueError:
                continue
            name_column = frame.geometry.name
            for _, row in frame.iterrows():
                geometry = row.geometry
                if not _has_geometry(geometry):
                    continue
                properties = {
                    key: value for key, value in row.items() if key != name_column
                }
                properties["feed_id"] = entry.feed_id
                properties["feed_color"] = entry.color
                features.append(
                    _geojson_feature(geometry.__geo_interface__, properties)
                )
        return {"type": "FeatureCollection", "features": features}

    @app.get("/api/shapes")
    def shapes_geojson():
        with lock:
            return _shapes_geojson()

    def _shapes_geojson():
        features = []
        for entry in registry.active_entries():
            try:
                frame = entry.editor.shapes
            except ValueError:
                continue
            route_types = _shape_route_types(entry.editor)
            for _, row in frame.iterrows():
                if not _has_geometry(row.geometry):
                    continue
                properties = {
                    "shape_id": row["shape_id"],
                    "feed_id": entry.feed_id,
                    "feed_color": entry.color,
                }
                route_type = route_types.get(_clean_id(row["shape_id"]))
                if route_type is not None:
                    properties["route_type"] = route_type
                features.append(
                    _geojson_feature(row.geometry.__geo_interface__, properties)
                )
        return {"type": "FeatureCollection", "features": features}

    @app.post("/api/stops")
    def add_stop(payload: dict = Body(...)):
        try:
            with lock:
                current_editor().add_stop(
                    payload["stop_id"],
                    payload["stop_name"],
                    _finite(payload["stop_lat"], "stop_lat"),
                    _finite(payload["stop_lon"], "stop_lon"),
                )
        except KeyError as error:
            raise HTTPException(422, f"missing field {error}") from None
        except (TypeError, ValueError) as error:
            raise HTTPException(422, str(error)) from None
        return {"ok": True}

    @app.patch("/api/stops/{stop_id:path}")
    def update_stop(stop_id: str, payload: dict = Body(...)):
        try:
            with lock:
                current_editor().update_stop(stop_id, **payload)
        except AttributeError:
            raise HTTPException(
                501, "this operation needs a loaded feed (FeedEditor)"
            ) from None
        except ValueError as error:
            raise HTTPException(404, str(error)) from None
        except TypeError as error:
            raise HTTPException(422, str(error)) from None
        return {"ok": True}

    @app.post("/api/agencies")
    def add_agency(payload: dict = Body(...)):
        try:
            with lock:
                current_editor().add_agency(
                    payload["agency_id"],
                    payload["agency_name"],
                    payload["agency_url"],
                    payload["agency_timezone"],
                )
        except KeyError as error:
            raise HTTPException(422, f"missing field {error}") from None
        except (TypeError, ValueError) as error:
            raise HTTPException(422, str(error)) from None
        return {"ok": True}

    @app.post("/api/services")
    def add_service(payload: dict = Body(...)):
        try:
            with lock:
                current_editor().add_service(
                    payload["service_id"],
                    payload["days"],
                    payload["start_date"],
                    payload["end_date"],
                )
        except KeyError as error:
            raise HTTPException(422, f"missing field {error}") from None
        except (TypeError, ValueError) as error:
            raise HTTPException(422, str(error)) from None
        return {"ok": True}

    @app.post("/api/routes")
    def add_route(payload: dict = Body(...)):
        try:
            with lock:
                current_editor().add_route(
                    payload["route_id"],
                    int(payload["route_type"]),
                    payload["route_short_name"],
                    agency_id=payload.get("agency_id"),
                )
        except KeyError as error:
            raise HTTPException(422, f"missing field {error}") from None
        except (TypeError, ValueError) as error:
            raise HTTPException(422, str(error)) from None
        return {"ok": True}

    @app.patch("/api/routes/{route_id:path}")
    def update_route(route_id: str, payload: dict = Body(...)):
        try:
            with lock:
                current_editor().update_route(route_id, **payload)
        except AttributeError:
            raise HTTPException(
                501, "this operation needs a loaded feed (FeedEditor)"
            ) from None
        except ValueError as error:
            raise HTTPException(404, str(error)) from None
        except TypeError as error:
            raise HTTPException(422, str(error)) from None
        return {"ok": True}

    @app.delete("/api/routes/{route_id:path}")
    def drop_route(route_id: str):
        try:
            with lock:
                current_editor().drop_route(route_id)
        except AttributeError:
            raise HTTPException(
                501, "this operation needs a loaded feed (FeedEditor)"
            ) from None
        except ValueError as error:
            raise HTTPException(404, str(error)) from None
        return {"ok": True}

    @app.post("/api/trips")
    def add_trip(payload: dict = Body(...)):
        try:
            with lock:
                current_editor().add_trip(
                    payload["route_id"],
                    payload["service_id"],
                    payload["trip_id"],
                    [tuple(stop) for stop in payload["stops"]],
                    shape_id=payload.get("shape_id"),
                )
        except KeyError as error:
            raise HTTPException(422, f"missing field {error}") from None
        except (TypeError, ValueError) as error:
            raise HTTPException(422, str(error)) from None
        return {"ok": True}

    @app.post("/api/trips/{trip_id:path}/shift")
    def shift_trip(trip_id: str, payload: dict = Body(...)):
        try:
            with lock:
                current_editor().shift_trip(trip_id, int(payload["seconds"]))
        except AttributeError:
            raise HTTPException(
                501, "this operation needs a loaded feed (FeedEditor)"
            ) from None
        except KeyError as error:
            raise HTTPException(422, f"missing field {error}") from None
        except (TypeError, ValueError) as error:
            raise HTTPException(422, str(error)) from None
        return {"ok": True}

    @app.post("/api/frequencies/headway")
    def set_headway(payload: dict = Body(...)):
        try:
            with lock:
                current_editor().set_headway(
                    payload["trip_id"],
                    payload["headway"],
                    window=payload.get("window"),
                    start=payload.get("start"),
                    end=payload.get("end"),
                )
        except AttributeError:
            raise HTTPException(
                501, "this operation needs a loaded feed (FeedEditor)"
            ) from None
        except KeyError as error:
            raise HTTPException(422, f"missing field {error}") from None
        except (TypeError, ValueError) as error:
            raise HTTPException(422, str(error)) from None
        return {"ok": True}

    @app.post("/api/trips/frequency")
    def add_frequency_trip(payload: dict = Body(...)):
        try:
            with lock:
                current_editor().add_frequency_trip(
                    payload["route_id"],
                    payload["service_id"],
                    payload["trip_id"],
                    [(stop, offset) for stop, offset in payload["stops"]],
                    start=payload["start"],
                    end=payload["end"],
                    headway=payload["headway"],
                    shape_id=payload.get("shape_id"),
                )
        except KeyError as error:
            raise HTTPException(422, f"missing field {error}") from None
        except (TypeError, ValueError) as error:
            raise HTTPException(422, str(error)) from None
        return {"ok": True}

    @app.post("/api/shapes")
    def add_shape(payload: dict = Body(...)):
        try:
            with lock:
                current_editor().add_shape(payload["shape_id"], payload["points"])
        except KeyError as error:
            raise HTTPException(422, f"missing field {error}") from None
        except (TypeError, ValueError) as error:
            raise HTTPException(422, str(error)) from None
        return {"ok": True}

    @app.post("/api/shapes/snap")
    def snap(payload: dict = Body(...)):
        if osm_state["source"] is None:
            raise HTTPException(
                409,
                "no OSM extract configured; start with an extract or acquire one "
                "via POST /api/osm/download",
            )
        from transitio.edit import snap_to_network

        custom_filter = payload.get("custom_filter", snap_custom_filter)
        if custom_filter is not None and not isinstance(custom_filter, dict):
            raise HTTPException(422, "custom_filter must be an object")
        waypoints = payload.get("waypoints")
        if waypoints is None:
            raise HTTPException(422, "missing field 'waypoints'")
        try:
            with lock:
                editor = osm_state["editor"]
                if editor is not None:
                    # Snap along the edited network so shapes follow edits.
                    line = editor.snap(
                        waypoints,
                        network_type=network_type,
                        custom_filter=custom_filter,
                    )
                elif custom_filter is not None:
                    line = snap_to_network(
                        waypoints, osm_state["source"], custom_filter=custom_filter
                    )
                else:
                    line = snap_to_network(
                        waypoints, osm_state["source"], network_type=network_type
                    )
        except ImportError as error:
            raise HTTPException(501, str(error)) from None
        except ValueError as error:
            raise HTTPException(422, str(error)) from None
        return {"type": "Feature", "geometry": line.__geo_interface__}

    @app.get("/api/routes")
    def routes_list():
        from transitio_editor import _timetable

        with lock:
            return {"routes": _timetable.list_routes(current_editor())}

    @app.get("/api/routes/{route_id:path}/trips")
    def route_trips(route_id: str):
        from transitio_editor import _timetable

        with lock:
            return {"trips": _timetable.list_trips(current_editor(), route_id)}

    @app.get("/api/trips/{trip_id:path}/times")
    def get_trip_times(trip_id: str):
        from transitio_editor import _timetable

        with lock:
            records = _timetable.trip_times(current_editor(), trip_id)
        if records is None:
            raise HTTPException(404, f"no trip {trip_id}")
        return {"trip_id": trip_id, "times": records}

    @app.put("/api/trips/{trip_id:path}/times")
    def put_trip_times(trip_id: str, payload: dict = Body(...)):
        from transitio_editor import _timetable

        try:
            with lock:
                _timetable.set_trip_times(current_editor(), trip_id, payload["times"])
        except KeyError as error:
            raise HTTPException(422, f"missing field {error}") from None
        except LookupError as error:
            raise HTTPException(404, str(error)) from None
        except (TypeError, ValueError, AttributeError) as error:
            raise HTTPException(422, str(error)) from None
        return {"ok": True}

    @app.delete("/api/trips/{trip_id:path}")
    def delete_trip(trip_id: str):
        from transitio_editor import _timetable

        try:
            with lock:
                _timetable.drop_trip(current_editor(), trip_id)
        except LookupError as error:
            raise HTTPException(404, str(error)) from None
        return {"ok": True}

    @app.post("/api/validate")
    def validate(payload: dict = Body(default={})):
        """Validate the current in-memory feed without persisting it."""
        import tempfile

        try:
            with lock, tempfile.TemporaryDirectory() as scratch:
                report = current_editor().save(
                    os.path.join(scratch, "current.zip"),
                    check=False,
                    change_log=False,
                    **payload,
                )
        except (TypeError, ValueError) as error:
            raise HTTPException(422, str(error)) from None
        return {"report": report}

    @app.post("/api/save")
    def save(payload: dict = Body(default={})):
        # Resolve the target and save under one lock so a concurrent
        # current-feed change can't save the wrong feed to a path.
        with lock:
            entry = registry.current_entry()
            if entry is None:
                raise HTTPException(409, "no feed loaded")
            target = payload.get("path") or entry.source
            if target is None:
                raise HTTPException(422, "no output path: pass {'path': ...}")
            if not str(target).endswith(".zip"):
                raise HTTPException(422, "output path must end in .zip")
            try:
                report = entry.editor.save(target, check=payload.get("check", True))
            except InvalidFeedError as error:
                # the file IS written; only the notice gate raised
                entry.source = os.fspath(target)
                return {"saved": True, "clean": False, "report": error.report}
            except (TypeError, ValueError) as error:
                raise HTTPException(422, str(error)) from None
            # a sourceless (merged/cropped/built) feed becomes sourced once
            # saved, so later session saves reference it instead of
            # embedding a stale copy
            entry.source = os.fspath(target)
            clean = not any(
                notice["severity"] == "ERROR" for notice in report["notices"]
            )
            return {"saved": True, "clean": clean, "report": report}

    @app.get("/api/catalogue")
    def catalogue_list():
        with lock:
            return {
                "feeds": [entry_dict(entry, registry) for entry in registry.entries()],
                "current": registry.current,
                "groups": registry.groups(),
            }

    @app.post("/api/catalogue/groups")
    def catalogue_group_add(payload: dict = Body(...)):
        name = _group_name(payload.get("name"))
        if name is None:
            raise HTTPException(422, "'name' must be 1-60 non-blank characters")
        with lock:
            if registry.has_group(name):
                raise HTTPException(422, f"group {name!r} already exists")
            return {"groups": registry.add_group(name)}

    @app.patch("/api/catalogue/groups")
    def catalogue_group_rename(payload: dict = Body(...)):
        # Names travel in the body, never the path: a group name is free
        # text and may contain a slash.
        name = payload.get("name")
        new_name = _group_name(payload.get("new_name"))
        if new_name is None:
            raise HTTPException(422, "'new_name' must be 1-60 non-blank characters")
        with lock:
            if not isinstance(name, str) or not registry.has_group(name):
                raise HTTPException(404, f"no group {name!r}")
            if new_name != name and registry.has_group(new_name):
                raise HTTPException(422, f"group {new_name!r} already exists")
            return {"groups": registry.rename_group(name, new_name)}

    @app.delete("/api/catalogue/groups")
    def catalogue_group_remove(name: str):
        # a query parameter, not a path segment: a group name may contain
        # a slash, and DELETE bodies are not carried by every client
        with lock:
            if not registry.has_group(name):
                raise HTTPException(404, f"no group {name!r}")
            # the feeds outlive their group; they just become ungrouped
            return {"groups": registry.remove_group(name)}

    @app.post("/api/catalogue")
    def catalogue_add(payload: dict = Body(...)):
        from transitio.edit import FeedEditor

        path_value = payload.get("path")
        if not isinstance(path_value, str):
            raise HTTPException(422, "'path' must be a string")
        path = Path(path_value)
        if not path.exists():
            raise HTTPException(404, f"feed not found: {path}")
        try:
            loaded = FeedEditor(path)
        except Exception as error:  # noqa: B902
            raise HTTPException(422, f"cannot load feed: {error}") from None
        name = payload.get("name")
        if name is not None and (
            not isinstance(name, str) or not _json_safe_name(name)
        ):
            raise HTTPException(422, "'name' must be a JSON-safe string")
        with lock:
            entry = registry.add(
                loaded,
                name or default_name(loaded),
                source=os.fspath(path),
            )
            return entry_dict(entry, registry)

    _SESSION_MARKER = ".transitio-session"

    def _session_paths(raw):
        from pathlib import Path

        if not isinstance(raw, str) or not raw.strip():
            raise HTTPException(422, "'path' must be a file path")
        try:
            path = Path(os.path.abspath(Path(raw).expanduser()))
        except (OSError, RuntimeError, ValueError) as error:
            # unknown ~user, NUL bytes: a clean 422, not a 500
            raise HTTPException(422, f"cannot use path: {error}") from None
        if path.suffix.lower() != ".json":
            raise HTTPException(422, "a session file must end in .json")
        return path, path.with_suffix(".data")

    def _prepare_session_data_dir(data_dir):
        # Never adopt a directory the session did not create: a user-chosen
        # session name must not make a like-named directory overwritable.
        marker = data_dir / _SESSION_MARKER
        try:
            if data_dir.is_symlink():
                raise HTTPException(422, f"{data_dir} is a symlink; refusing to use it")
            if data_dir.exists():
                if not marker.exists() and any(data_dir.iterdir()):
                    raise HTTPException(
                        422,
                        f"{data_dir} exists and is not a session data directory",
                    )
            else:
                data_dir.mkdir(parents=True)
            marker.touch()
        except HTTPException:
            raise
        except OSError as error:
            # a regular file where the directory would go, an unwritable
            # parent: a clean 422, never a 500
            raise HTTPException(422, f"cannot use {data_dir}: {error}") from None
        return data_dir

    def _publish_embedded(editor, target):
        # Write to a temp name, then hard-link onto the final one: the link
        # fails atomically if the name exists, so nothing is overwritten.
        import uuid

        temp = target.with_name(f".tmp-{uuid.uuid4().hex}")
        # claim the temp name exclusively first: editor.save publishes onto
        # it with os.replace, which must only ever replace our own
        # placeholder, never a planted file
        try:
            os.close(os.open(temp, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
        except FileExistsError:
            raise HTTPException(422, f"{temp} already exists") from None
        try:
            # session storage, not a user save: no change-log sidecar
            editor.save(temp, check=False, change_log=False)
            os.link(temp, target)
        except FileExistsError:
            raise HTTPException(422, f"{target} already exists") from None
        finally:
            temp.unlink(missing_ok=True)
            # a failed editor.save can leave its own staging file behind
            temp.with_name(temp.name + ".part").unlink(missing_ok=True)

    @app.post("/api/session/save")
    def session_save(payload: dict = Body(...)):
        """Write the loaded state to a session .json.

        Sourceless feeds (merged, cropped, built) are embedded as zips in
        a sibling ``<name>.data`` directory; sourced feeds are referenced
        by path, so edits made to them since their file was written are
        NOT captured — save the feed first to include them.
        """
        import json as json_module
        import tempfile
        import uuid
        from datetime import datetime, timezone

        session_path, data_dir = _session_paths(payload.get("path"))
        view = payload.get("view")
        if view is not None:
            if not isinstance(view, dict):
                raise HTTPException(422, "'view' must be an object")
            try:
                json_module.dumps(view, allow_nan=False, ensure_ascii=False).encode(
                    "utf-8"
                )
            except ValueError:  # UnicodeEncodeError is a ValueError
                raise HTTPException(422, "'view' must be plain JSON") from None
        with lock:
            entries = registry.entries()
            embedded = [entry for entry in entries if entry.source is None]
            save_id = uuid.uuid4().hex
            written = {}
            if embedded:
                _prepare_session_data_dir(data_dir)
                for index, entry in enumerate(embedded):
                    target = data_dir / (
                        f"{save_id}-{index}-{_feed_filename(entry.name)}"
                    )
                    try:
                        _publish_embedded(entry.editor, target)
                    except HTTPException:
                        raise
                    except (OSError, TypeError, ValueError) as error:
                        raise HTTPException(
                            422, f"cannot write {target}: {error}"
                        ) from None
                    written[entry.feed_id] = target
            feeds = []
            missing = []
            for entry in entries:
                if entry.feed_id in written:
                    source = written[entry.feed_id]
                    sha256 = _sha256_file(source)
                elif entry.source is not None:
                    source = os.path.abspath(entry.source)
                    try:
                        readable = os.path.isfile(source)
                        sha256 = _sha256_file(source) if readable else None
                    except OSError:
                        readable = False
                        sha256 = None
                    if not readable:
                        # recorded anyway (the file may come back), but the
                        # saver must hear that this feed cannot restore now
                        missing.append(entry.name)
                feeds.append(
                    {
                        "name": entry.name,
                        "color": entry.color,
                        "active": entry.active,
                        "current": registry.current == entry.feed_id,
                        "group": entry.group,
                        "origin": entry.origin,
                        "source": os.fspath(source),
                        "sha256": sha256,
                        "embedded": entry.feed_id in written,
                    }
                )
            session = {
                "transitio_editor_session": 1,
                "saved_at": datetime.now(timezone.utc).isoformat(),
                "groups": registry.groups(),
                "feeds": feeds,
                "osm_source": (
                    os.path.abspath(osm_state["source"])
                    if osm_state["source"]
                    else None
                ),
                "view": view or {},
            }
            try:
                json_module.dumps(session, allow_nan=False, ensure_ascii=False).encode(
                    "utf-8"
                )
            except ValueError:  # UnicodeEncodeError is a ValueError
                # e.g. a lone surrogate from a non-UTF-8 filename: restore
                # would refuse this file, so refuse to write it
                raise HTTPException(
                    422, "cannot serialise session (a name or path is not UTF-8)"
                ) from None
            temp = None
            try:
                session_path.parent.mkdir(parents=True, exist_ok=True)
                fd, temp = tempfile.mkstemp(
                    dir=session_path.parent, prefix=".session-", suffix=".part"
                )
                with os.fdopen(fd, "w") as handle:
                    json_module.dump(session, handle, indent=2)
                os.replace(temp, session_path)
            except OSError as error:
                if temp is not None:
                    try:
                        os.unlink(temp)
                    except OSError:
                        pass
                raise HTTPException(422, f"cannot write session: {error}") from None
            # the save is committed above; this tally is informational and
            # must not fail the request
            unreferenced = 0
            try:
                # only a directory this save (or an earlier one) marked as
                # session-owned is tallied; a like-named foreign directory
                # is none of our business
                if data_dir.is_dir() and (data_dir / _SESSION_MARKER).exists():
                    kept = {target.name for target in written.values()}
                    kept.add(_SESSION_MARKER)
                    # a sourced feed may legitimately point into the data
                    # directory (e.g. a zip loaded from it by hand)
                    kept |= {
                        os.path.basename(feed["source"])
                        for feed in feeds
                        if os.path.dirname(feed["source"]) == os.fspath(data_dir)
                    }
                    # everything else — older saves' zips, orphans of
                    # failed ones — is reclaimable-but-untouched
                    unreferenced = sum(
                        1
                        for item in data_dir.iterdir()
                        if item.is_file() and item.name not in kept
                    )
            except OSError:
                pass
            return {
                "path": os.fspath(session_path),
                "embedded": [entry.name for entry in embedded],
                "referenced": [
                    entry.name for entry in entries if entry.source is not None
                ],
                "unreferenced_data_files": unreferenced,
                "missing": missing,
            }

    @app.post("/api/session/restore")
    def session_restore(payload: dict = Body(...)):
        """Rebuild the loaded state from a session .json.

        Replacing loaded feeds/groups needs ``replace: true``; discarding
        unsaved OSM network edits needs ``discard_edits: true`` — two
        separate consents. Missing feed files are skipped and reported.
        """
        import json as json_module

        from transitio.edit import FeedEditor

        session_path, _ = _session_paths(payload.get("path"))
        replace = payload.get("replace", False)
        discard_edits = payload.get("discard_edits", False)
        if not isinstance(replace, bool) or not isinstance(discard_edits, bool):
            raise HTTPException(422, "'replace' and 'discard_edits' must be booleans")
        with lock:
            # parse inside the lock, so a restore racing a save of the same
            # file cannot rebuild from a stale snapshot
            # regular files only: a FIFO would block every request behind
            # the app lock
            if not session_path.is_file():
                raise HTTPException(422, f"not a session file: {session_path}")
            try:
                session = json_module.loads(session_path.read_text(encoding="utf-8"))
            except OSError as error:
                raise HTTPException(422, f"cannot read session: {error}") from None
            except ValueError as error:
                raise HTTPException(422, f"not a session file: {error}") from None
            version = (
                session.get("transitio_editor_session")
                if isinstance(session, dict)
                else None
            )
            if isinstance(version, bool) or version != 1:
                raise HTTPException(422, "not a transitio-editor session file")
            # required, never defaulted: a truncated file must not read as
            # an intentionally empty session
            required = ("groups", "feeds", "view", "osm_source")
            if any(key not in session for key in required):
                raise HTTPException(422, "malformed session file")
            groups = session["groups"]
            records = session["feeds"]
            view = session["view"]
            osm_source = session["osm_source"]
            if osm_source is not None and not isinstance(osm_source, str):
                raise HTTPException(422, "malformed session file")

            try:
                json_module.dumps(session, allow_nan=False, ensure_ascii=False).encode(
                    "utf-8"
                )
            except ValueError:  # UnicodeEncodeError is a ValueError
                raise HTTPException(422, "malformed session file") from None

            def _record_ok(record):
                # every field the save writes must be present and typed;
                # format growth adds NEW keys, which stay ignorable
                if not isinstance(record, dict):
                    return False
                strings = ("name", "source", "sha256", "color", "group", "origin")
                flags = ("active", "current", "embedded")
                if any(key not in record for key in strings + flags):
                    return False
                if any(
                    record[key] is not None and not isinstance(record[key], str)
                    for key in strings
                ):
                    return False
                if any(not isinstance(record[key], bool) for key in flags):
                    return False
                if not isinstance(record["name"], str) or not isinstance(
                    record["source"], str
                ):
                    return False
                return _json_safe_name(record["name"])

            groups_ok = isinstance(groups, list) and all(
                isinstance(group, str) and _group_name(group) == group
                for group in groups
            )
            if (
                not groups_ok
                or len(set(groups)) != len(groups)
                or not isinstance(records, list)
                or not all(_record_ok(record) for record in records)
                or (
                    bool(records)
                    and sum(1 for record in records if record.get("current")) != 1
                )
                or any(
                    record.get("group") is not None
                    and record.get("group") not in groups
                    for record in records
                )
                or not isinstance(view, dict)
            ):
                # malformed sessions fail before anything is touched
                raise HTTPException(422, "malformed session file")
            loaded = [
                entry
                for entry in registry.entries()
                if entry.source is not None or entry.editor.tables
            ]
            if (loaded or registry.groups()) and not replace:
                raise HTTPException(409, {"reason": "feeds", "feeds": len(loaded)})
            if osm_state["dirty"] and not discard_edits:
                raise HTTPException(409, {"reason": "osm-edits"})

            registry.reset()
            for group in groups:
                registry.add_group(group)
            skipped, warnings = [], []
            current_id = None
            for record in records:
                name = record["name"]
                source = record.get("source")
                # regular files only: a FIFO here would block the app lock
                if not isinstance(source, str) or not os.path.isfile(source):
                    skipped.append(
                        {"name": name, "reason": f"file not found: {source}"}
                    )
                    continue
                try:
                    recorded = record.get("sha256")
                    changed = bool(recorded) and _sha256_file(source) != recorded
                    editor = FeedEditor(source)
                except Exception as error:  # noqa: B902
                    # vanished or unreadable mid-restore: a skip, not a 500
                    skipped.append({"name": name, "reason": str(error)})
                    continue
                if changed:
                    warnings.append(f"{name}: changed since the session was saved")
                entry = registry.add(
                    editor,
                    name,
                    # an embedded zip is session storage, not a user file:
                    # the entry stays sourceless so the next save embeds
                    # its then-current tables
                    source=None if record.get("embedded") else source,
                    origin=record.get("origin"),
                    group=record.get("group"),
                    color=record.get("color"),
                )
                entry.active = bool(record.get("active", True))
                if record.get("current"):
                    current_id = entry.feed_id
            if current_id is not None:
                registry.current = current_id
            elif registry.entries() and any(
                record.get("current") for record in records
            ):
                warnings.append(
                    "the session's current feed was skipped; "
                    "the first restored feed is current"
                )

            osm_state["editor"] = None
            osm_state["dirty"] = False
            if isinstance(osm_source, str) and os.path.isfile(osm_source):
                osm_state["source"] = osm_source
            else:
                if osm_source:
                    warnings.append(f"OSM extract not found: {osm_source}")
                osm_state["source"] = None
            return {
                "feeds": [entry_dict(entry, registry) for entry in registry.entries()],
                "groups": registry.groups(),
                "current": registry.current,
                "skipped": skipped,
                "warnings": warnings,
                "view": view,
            }

    @app.post("/api/catalogue/merge")
    def catalogue_merge(payload: dict = Body(...)):
        from transitio.gtfs import merge_tables

        feed_ids = payload.get("feed_ids")
        if not isinstance(feed_ids, list) or not all(
            isinstance(feed_id, str) for feed_id in feed_ids
        ):
            raise HTTPException(422, "'feed_ids' must be a list of strings")
        if len(feed_ids) < 2:
            raise HTTPException(422, "merging needs at least two feeds")
        if len(set(feed_ids)) != len(feed_ids):
            raise HTTPException(422, "a feed cannot be merged with itself")
        directory = payload.get("directory")
        if directory is not None:
            directory = _prepared_directory(directory, "output directory")
        with lock:
            entries = []
            for feed_id in feed_ids:
                entry = registry.get(feed_id)
                if entry is None:
                    raise HTTPException(422, f"no feed {feed_id}")
                entries.append(entry)
            prefixes = _merge_prefixes(
                [entry.name for entry in entries], [entry.feed_id for entry in entries]
            )
            try:
                tables, dropped = merge_tables(
                    [entry.editor.tables for entry in entries],
                    prefixes=prefixes,
                    extra_entries=[
                        list(getattr(entry.editor, "_extra_entries", {}))
                        for entry in entries
                    ],
                )
            except (TypeError, ValueError) as error:
                raise HTTPException(422, str(error)) from None
            name = str(payload.get("name") or "").strip()
            if not name:
                name = " + ".join(entry.name for entry in entries)[:60]
            editor = _editor_from_tables(tables)
            # With an output folder the merged feed is written there and the
            # entry keeps that path, so saving later goes back to the file.
            saved = None
            if directory is not None:
                target = directory / _feed_filename(name)
                # Never clobber a feed that is already there (nor follow a
                # symlink planted at the target: transitio's save refuses).
                if target.exists() or target.is_symlink():
                    raise HTTPException(409, f"{target} already exists")
                try:
                    editor.save(target, check=False)
                except (OSError, TypeError, ValueError) as error:
                    raise HTTPException(
                        422, f"cannot write merged feed: {error}"
                    ) from None
                saved = os.fspath(target)
            merged = registry.add(editor, name, source=saved)
            registry.current = merged.feed_id
            return {
                **entry_dict(merged, registry),
                "dropped_files": dropped,
                "saved": saved,
            }

    @app.post("/api/catalogue/crop")
    def catalogue_crop(payload: dict = Body(...)):
        import tempfile

        from transitio.edit import FeedEditor
        from transitio.gtfs import crop_feed

        area = _crop_area(payload.get("shape"))
        if area is None:
            raise HTTPException(
                422, "'shape' must be a GeoJSON polygon or [minx, miny, maxx, maxy]"
            )
        full_trips_only = payload.get("full_trips_only", False)
        if not isinstance(full_trips_only, bool):
            raise HTTPException(422, "'full_trips_only' must be a boolean")
        feed_ids = payload.get("feed_ids")
        if feed_ids is not None:
            if not isinstance(feed_ids, list) or not all(
                isinstance(feed_id, str) for feed_id in feed_ids
            ):
                raise HTTPException(422, "'feed_ids' must be a list of strings")
            if len(set(feed_ids)) != len(feed_ids):
                # cropping one feed twice would just cost twice as much
                raise HTTPException(422, "a feed cannot be cropped twice")
        group = "Cropped feeds"
        if payload.get("group") is not None:
            group = _group_name(payload.get("group"))
            if group is None:
                raise HTTPException(422, "'group' must be 1-60 non-blank characters")

        with lock:
            if feed_ids is None:
                sources = registry.active_entries()
            else:
                sources = []
                for feed_id in feed_ids:
                    entry = registry.get(feed_id)
                    if entry is None:
                        raise HTTPException(422, f"no feed {feed_id}")
                    sources.append(entry)
            if not sources:
                raise HTTPException(422, "no feeds to crop")

            created, empty, skipped = [], [], []
            # Serialise and crop under the lock: an edit landing between
            # reading a feed and writing it out would tear the snapshot.
            with tempfile.TemporaryDirectory() as scratch:
                for index, entry in enumerate(sources):
                    staged = os.path.join(scratch, f"in-{index}.zip")
                    cropped = os.path.join(scratch, f"out-{index}.zip")
                    try:
                        entry.editor.save(staged, check=False, change_log=False)
                        crop_feed(
                            staged, cropped, aoi=area, full_trips_only=full_trips_only
                        )
                        loaded = FeedEditor(cropped)
                    except Exception as error:  # noqa: B902
                        # the area was validated before any work started, so
                        # what is left is this feed's problem
                        skipped.append({"name": entry.name, "reason": str(error)})
                        continue
                    if not len(loaded.tables.get("stops.txt", ())):
                        empty.append(entry.name)
                        continue
                    # pair each result with its source: names repeat, so
                    # they cannot be used to match them up afterwards
                    created.append((entry, loaded))

            if created and not registry.has_group(group):
                registry.add_group(group)
            entries = [
                registry.add(loaded, f"{source.name} (cropped)", group=group)
                for source, loaded in created
            ]
            return {
                "feeds": [entry_dict(entry, registry) for entry in entries],
                "empty": empty,
                "skipped": skipped,
                "groups": registry.groups(),
            }

    @app.put("/api/catalogue/current")
    def catalogue_set_current(payload: dict = Body(...)):
        feed_id = payload.get("feed_id")
        if not isinstance(feed_id, str):
            raise HTTPException(422, "'feed_id' must be a string")
        with lock:
            if registry.get(feed_id) is None:
                raise HTTPException(404, f"no feed {feed_id}")
            registry.current = feed_id
            return {"current": registry.current}

    @app.patch("/api/catalogue/{feed_id:path}")
    def catalogue_update(feed_id: str, payload: dict = Body(...)):
        with lock:
            entry = registry.get(feed_id)
            if entry is None:
                raise HTTPException(404, f"no feed {feed_id}")
            # validate every field first: a rejected one must not leave
            # the others already applied
            if "active" in payload and not isinstance(payload["active"], bool):
                raise HTTPException(422, "'active' must be a boolean")
            if "group" in payload and payload["group"] is not None:
                # never create a group implicitly: a typo would file the
                # feed somewhere the user cannot see
                group = payload["group"]
                if not isinstance(group, str) or not registry.has_group(group):
                    raise HTTPException(422, f"no group {group!r}")
            if "active" in payload:
                entry.active = payload["active"]
            if "name" in payload:
                if not isinstance(payload["name"], str) or not _json_safe_name(
                    payload["name"]
                ):
                    raise HTTPException(422, "'name' must be a JSON-safe string")
                entry.name = payload["name"]
            if "group" in payload:
                entry.group = payload["group"]
            return entry_dict(entry, registry)

    @app.delete("/api/catalogue/{feed_id:path}")
    def catalogue_remove(feed_id: str):
        with lock:
            if registry.remove(feed_id) is None:
                raise HTTPException(404, f"no feed {feed_id}")
            return {"ok": True, "current": registry.current}

    def _feed_result(feed):
        return {
            "id": feed.id,
            "provider": feed.provider,
            "status": feed.status,
            "official": feed.official,
            "locations": [
                {
                    "country": location.get("country_code"),
                    "subdivision": location.get("subdivision_name"),
                    "municipality": location.get("municipality"),
                }
                for location in feed.locations
            ],
            "producer_url": feed.producer_url,
            "license_url": feed.license_url,
            "downloadable": bool(feed.latest_dataset_url),
        }

    def _parse_bbox(bbox):
        parts = bbox.split(",")
        try:
            values = [float(value) for value in parts]
        except ValueError:
            values = None
        if values is None or len(values) != 4 or not all(map(math.isfinite, values)):
            raise HTTPException(422, "bbox must be 'minx,miny,maxx,maxy'")
        minx, miny, maxx, maxy = values
        if not (-180 <= minx <= maxx <= 180 and -90 <= miny <= maxy <= 90):
            raise HTTPException(422, "bbox coordinates out of range or reversed")
        return (minx, miny, maxx, maxy)

    @app.get("/api/fs/dirs")
    def fs_dirs(path: str | None = None):
        # Directory listing for the folder and feed browsers (feeds are the
        # readable *.zip files, which is what a feed path can point at).
        # Same local-file trust model as loading a feed from a path or
        # saving to one: the loopback single user browses their own machine.
        try:
            base = Path(path).expanduser() if path else Path.home()
            base = base.resolve()
        except (OSError, RuntimeError, ValueError, KeyError) as error:
            # unknown ~user, symlink loops, NUL bytes: a clean 404, not a 500
            raise HTTPException(404, f"cannot resolve: {error}") from None
        if base.is_file():
            # pointed at a file (a typed feed path): browse its folder
            base = base.parent
        if not base.is_dir():
            raise HTTPException(404, f"not a directory: {base}")
        subdirs = []
        try:
            entries = list(base.iterdir())
        except PermissionError:
            raise HTTPException(403, f"not readable: {base}") from None
        except OSError as error:  # e.g. the directory vanished meanwhile
            raise HTTPException(404, f"cannot list: {error}") from None
        feeds = []
        sessions = []
        for entry in entries:
            try:
                if entry.name.startswith(".") or not _json_safe_name(entry.name):
                    continue
                if entry.is_dir():
                    # only offer directories the browser could descend into
                    if os.access(entry, os.R_OK | os.X_OK):
                        subdirs.append(entry.name)
                elif (
                    entry.suffix.lower() == ".zip"
                    # regular files only: a FIFO named *.zip would hang the
                    # load that follows picking it
                    and entry.is_file()
                    and os.access(entry, os.R_OK)
                ):
                    feeds.append(entry.name)
                elif (
                    entry.suffix.lower() == ".json"
                    and entry.is_file()
                    and os.access(entry, os.R_OK)
                ):
                    sessions.append(entry.name)
            except OSError:
                continue  # unreadable entry: skip it
        parent = os.fspath(base.parent) if base.parent != base else None
        return {
            "path": os.fspath(base),
            "parent": parent,
            "dirs": sorted(subdirs),
            "feeds": sorted(feeds),
            "sessions": sorted(sessions),
        }

    @app.get("/api/search")
    def search(
        q: str | None = None,
        country: str | None = None,
        subdivision: str | None = None,
        municipality: str | None = None,
        bbox: str | None = None,
        official: bool = False,
        limit: int = 50,
    ):
        place = None
        query = (q or "").strip()
        if query:
            # A typed place decides the area: geocode it and search the
            # feeds overlapping it, whatever the other area inputs say
            # (a stale bbox is ignored entirely, not validated).
            try:
                place = _place_bbox(query)
            except Exception as error:  # noqa: B902  (geocoder, no match)
                raise HTTPException(
                    422, f"cannot find place {query!r}: {error}"
                ) from None
            aoi = place
        else:
            aoi = _parse_bbox(bbox) if bbox else None
        client = get_catalog()
        try:
            feeds = client.search_feeds(
                aoi=aoi,
                country_code=country or None,
                subdivision=subdivision or None,
                municipality=municipality or None,
                official_only=official,
                limit=limit,
            )
        except Exception as error:  # noqa: B902
            raise HTTPException(502, f"catalog search failed: {error}") from None
        for feed in feeds:
            search_cache[feed.id] = feed
        # No refresh token means search_feeds served the CSV export, which
        # lacks historical datasets and hosted validation reports.
        csv_fallback = not getattr(client, "_refresh_token", None)
        result = {
            "feeds": [_feed_result(feed) for feed in feeds],
            "csv_fallback": csv_fallback,
        }
        if place is not None:
            # the frontend flies the map to the place the search meant
            result["place"] = {"query": query, "bbox": list(place)}
        return result

    @app.post("/api/catalogue/download")
    def catalogue_download(payload: dict = Body(...)):
        feed_id = payload.get("feed_id")
        if not isinstance(feed_id, str):
            raise HTTPException(422, "'feed_id' must be a string")
        activate = payload.get("activate", True)
        if not isinstance(activate, bool):
            raise HTTPException(422, "'activate' must be a boolean")
        aoi = payload.get("aoi")
        if aoi is not None:
            aoi = _acquire_bbox(aoi)  # validate before touching the network
        directory = payload.get("directory")
        if directory is not None:
            directory = _prepared_directory(directory, "download directory")
        feed = search_cache.get(feed_id)
        if feed is None:
            raise HTTPException(404, f"unknown feed {feed_id}; search for it first")
        if not feed.latest_dataset_url:
            raise HTTPException(422, f"feed {feed_id} has no downloadable dataset")

        from transitio.edit import FeedEditor

        # Download, optionally crop, and load outside the lock; only the
        # registry insert needs it. A given directory replaces the transitio
        # cache as the target (the AOI crop lands beside its download).
        try:
            path = get_catalog().download_latest(feed, directory=directory)
        except Exception as error:  # noqa: B902
            raise HTTPException(502, f"download failed: {error}") from None
        source = path
        if aoi is not None:
            source = _crop_downloaded_feed(path, aoi, feed)
        try:
            loaded = FeedEditor(source)
        except Exception as error:  # noqa: B902
            if aoi is not None:  # discard the unreadable crop (keep the cache)
                try:
                    os.unlink(source)
                except OSError:
                    pass
            raise HTTPException(422, f"cannot load feed: {error}") from None
        with lock:
            entry = registry.add(
                loaded,
                feed.provider or feed.id,
                source=os.fspath(source),
                origin=feed.id,
            )
            entry.active = activate
            return entry_dict(entry, registry)

    def _crop_downloaded_feed(path, aoi, feed):
        # Crop the downloaded GTFS to the AOI bbox and drop a provenance
        # sidecar recording the source dataset, bbox and resulting row counts.
        import datetime
        import hashlib
        import json
        import shutil
        import tempfile

        from transitio.gtfs import crop_feed

        source = Path(os.fspath(path))
        # Co-locate the crop with its downloaded source, keyed by the AOI: a
        # different area gets a different file (never overwriting another
        # entry's), re-cropping the same area is idempotent, and the crop shares
        # the download cache's lifecycle rather than orphaning a temp dir.
        tag = hashlib.sha1(repr(tuple(aoi)).encode()).hexdigest()[:12]
        cropped = source.with_name(f"{source.stem}.aoi-{tag}.zip")
        # Crop into a private temp dir, then publish atomically, so a failed or
        # concurrent same-AOI crop can't leave a partial file or delete one a
        # reader holds.
        stage = tempfile.mkdtemp(dir=os.fspath(source.parent), prefix=".aoicrop-")
        try:
            staged = os.path.join(stage, "crop.zip")
            result = crop_feed(os.fspath(source), staged, aoi=aoi)
            os.replace(staged, os.fspath(cropped))
        except Exception as error:  # noqa: B902
            raise HTTPException(422, f"crop failed: {error}") from None
        finally:
            shutil.rmtree(stage, ignore_errors=True)
        provenance = {
            "source_dataset": feed.latest_dataset_url,
            "aoi_bbox": list(aoi),
            "row_counts": (
                result.get("row_counts") if isinstance(result, dict) else None
            ),
            "cropped_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }
        _write_sidecar(
            os.fspath(cropped) + ".provenance.json", json.dumps(provenance, indent=2)
        )
        return cropped

    @app.get("/api/network/nodes")
    def network_nodes():
        with lock:
            return _network_features(get_osm_editor().nodes)

    @app.get("/api/network/ways")
    def network_ways():
        with lock:
            return _network_features(get_osm_editor().ways)

    @app.get("/api/network")
    def network_summary():
        # Source and counts let the catalogue list the OSM extract alongside
        # the GTFS feeds; counts exist only once the network is loaded.
        with lock:
            body = {"available": osm_state["source"] is not None}
            if osm_state["source"] is not None:
                body["source"] = os.fspath(osm_state["source"])
                editor = osm_state["editor"]
                if editor is not None:
                    body["nodes"] = int(len(editor.nodes))
                    body["ways"] = int(len(editor.ways))
        return body

    def _network_int_id(raw):
        # Provisional elements carry negative ids. Parse exactly (no float,
        # which would round ids past 2**53 or accept exponent notation) and
        # reject non-integers rather than coercing a bool to an element.
        if isinstance(raw, bool):
            raise HTTPException(422, "id must be an integer")
        if isinstance(raw, int):
            return raw
        if isinstance(raw, str):
            try:
                return int(raw, 10)
            except ValueError:
                raise HTTPException(422, "id must be an integer") from None
        raise HTTPException(422, "id must be an integer")

    # Tag keys OsmEditor refuses as tags (identity/geometry/metadata) plus its
    # mutation-method parameter names; rejecting them here keeps a bad key from
    # colliding with a keyword argument (TypeError) or failing only after the
    # draw's nodes and splits are already applied.
    _reserved_tag_keys = frozenset(
        {
            "id",
            "osm_type",
            "nodes",
            "geometry",
            "lon",
            "lat",
            "u",
            "v",
            "length",
            "tags",
            "timestamp",
            "version",
            "changeset",
            "visible",
            "node_ids",
            "way_id",
            "node_id",
            "self",
        }
    )

    def _network_tags(payload):
        if "tags" not in payload:
            return {}
        tags = payload["tags"]
        if not isinstance(tags, dict):  # an explicit null/list is malformed
            raise HTTPException(422, "'tags' must be an object")
        clean = {}
        for key, value in tags.items():
            if not isinstance(value, str):
                raise HTTPException(422, f"tag '{key}' value must be a string")
            if str(key) in _reserved_tag_keys:
                raise HTTPException(422, f"reserved tag key '{key}'")
            clean[str(key)] = value
        return clean

    def _network_coord(payload, key):
        if key not in payload:
            raise HTTPException(422, f"missing '{key}'")
        value = payload[key]
        if isinstance(value, bool):  # float(True) == 1.0 would slip through
            raise HTTPException(422, f"'{key}' must be a number")
        try:
            return _finite(value, key)
        except (TypeError, ValueError, OverflowError) as error:
            raise HTTPException(422, str(error) or "invalid coordinate") from None

    def _network_lonlat(payload):
        lon = _network_coord(payload, "lon")
        lat = _network_coord(payload, "lat")
        if not (-180 <= lon <= 180 and -90 <= lat <= 90):
            raise HTTPException(422, "coordinates out of WGS84 range")
        return lon, lat

    def _edit_network(action):
        try:
            result = action()
        except ValueError as error:
            message = str(error)
            status = 404 if message.startswith("no ") else 422
            raise HTTPException(status, message) from None
        # Any successful mutation (add/move/delete/retag) marks the network
        # dirty; in-place edits leave no trace in the editor's own id sets.
        osm_state["dirty"] = True
        return result

    @app.post("/api/network/nodes")
    def network_add_node(payload: dict = Body(...)):
        lon, lat = _network_lonlat(payload)
        tags = _network_tags(payload)
        with lock:
            editor = get_osm_editor()
            node_id = _edit_network(lambda: editor.add_node(lon, lat, **tags))
        return {"id": node_id}

    @app.patch("/api/network/nodes/{node_id}")
    def network_update_node(node_id: str, payload: dict = Body(...)):
        target = _network_int_id(node_id)
        # Validate everything before touching the editor so a bad tag can't
        # leave a half-applied move.
        if ("lon" in payload) != ("lat" in payload):
            raise HTTPException(422, "a move needs both 'lon' and 'lat'")
        move = _network_lonlat(payload) if "lon" in payload else None
        tags = _network_tags(payload)
        with lock:
            editor = get_osm_editor()
            # Tags first (they carry the reserved-key check); a failure here
            # returns before the move, keeping the PATCH atomic.
            if tags:
                _edit_network(lambda: editor.retag_node(target, **tags))
            if move is not None:
                _edit_network(lambda: editor.move_node(target, *move))
        return {"ok": True}

    @app.delete("/api/network/nodes/{node_id}")
    def network_delete_node(node_id: str):
        target = _network_int_id(node_id)
        with lock:
            editor = get_osm_editor()
            _edit_network(lambda: editor.delete_node(target))
        return {"ok": True}

    @app.post("/api/network/save")
    def network_save(payload: dict = Body(...)):
        import datetime
        import json
        from pathlib import Path

        path_value = payload.get("path")
        if not isinstance(path_value, str) or not path_value:
            raise HTTPException(422, "'path' must be a non-empty string")
        if not path_value.endswith(".pbf"):
            raise HTTPException(422, "path must end with .pbf")
        if "\x00" in path_value:
            raise HTTPException(422, "path must not contain NUL bytes")
        target = Path(path_value)
        with lock:
            # A network-only save drops non-network features, so refuse to
            # write over the source extract. Read the source under the lock so
            # a concurrent acquisition can't swap it mid-save. An unresolvable
            # path (symlink loop, NUL byte) can't be the source.
            source = osm_state["source"]
            if source is not None:
                source_path = Path(os.fspath(source))
                try:
                    aliases = target.resolve() == source_path.resolve()
                    # A hard link resolves to a different path but the same
                    # inode; catch that when the target already exists.
                    if not aliases and target.exists() and source_path.exists():
                        aliases = target.samefile(source_path)
                except (OSError, RuntimeError, ValueError):
                    aliases = False
                if aliases:
                    raise HTTPException(
                        422,
                        "refusing to overwrite the source extract; save to a new "
                        "path",
                    )
            editor = get_osm_editor()
            try:
                editor.save(target)
            except ValueError as error:  # e.g. a symlink target
                raise HTTPException(422, str(error)) from None
            except Exception as error:  # noqa: B902
                raise HTTPException(500, f"save failed: {error}") from None
            # Provenance sidecar for reproducibility (source, edit counts, time).
            # Count only ids created this session; negative ids loaded from an
            # editor-produced extract must not read as fresh additions.
            provisional = getattr(editor, "_provisional", set())
            provenance = {
                "source": os.fspath(source) if source else None,
                "added_nodes": int(editor.nodes["id"].isin(provisional).sum()),
                "added_ways": int(editor.ways["id"].isin(provisional).sum()),
                "saved_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            }
            _write_sidecar(
                os.fspath(target) + ".provenance.json",
                json.dumps(provenance, indent=2),
            )
            osm_state["dirty"] = False  # edits are now persisted
        return {"saved": True, "path": os.fspath(target)}

    @app.post("/api/network/reset")
    def network_reset():
        with lock:
            previous = osm_state["editor"]
            osm_state["editor"] = None
            try:
                get_osm_editor()  # reload now so a bad source fails here
            except HTTPException:
                osm_state["editor"] = previous  # keep the working editor
                raise
            osm_state["dirty"] = False  # reloaded from source, edits discarded
        return {"ok": True}

    @app.get("/api/network/features")
    def network_features_snapshot():
        # Nodes and ways from one locked read, so the client never renders a
        # mix of two editor generations.
        with lock:
            editor = get_osm_editor()
            return {
                "nodes": _network_features(editor.nodes),
                "ways": _network_features(editor.ways),
            }

    def _acquire_bbox(bbox):
        if not isinstance(bbox, list) or len(bbox) != 4:
            raise HTTPException(422, "'bbox' must be [minx, miny, maxx, maxy]")
        values = []
        for value in bbox:
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise HTTPException(422, "bbox values must be numbers")
            try:
                number = float(value)
            except OverflowError:
                raise HTTPException(422, "bbox value out of range") from None
            if not math.isfinite(number):
                raise HTTPException(422, "bbox values must be finite")
            values.append(number)
        minx, miny, maxx, maxy = values
        if not (-180 <= minx <= 180 and -180 <= maxx <= 180):
            raise HTTPException(422, "longitudes must be within [-180, 180]")
        if not (-90 <= miny <= 90 and -90 <= maxy <= 90):
            raise HTTPException(422, "latitudes must be within [-90, 90]")
        if not (minx < maxx and miny < maxy):
            raise HTTPException(422, "bbox must have positive area")
        return (minx, miny, maxx, maxy)

    def _extract_name(url):
        # A readable name from a Geofabrik PBF URL, e.g.
        # ".../europe/finland-latest.osm.pbf" -> "finland".
        base = url.rsplit("/", 1)[-1]
        for suffix in ("-latest.osm.pbf", ".osm.pbf", ".pbf"):
            if base.endswith(suffix):
                return base[: -len(suffix)]
        return base

    def _resolve_extract(aoi):
        # Normalise the AOI and resolve the covering Geofabrik extract from
        # pyrosm's bundled index — no download.
        from transitio.osm._fetch import _as_geometry, _resolve_url

        try:
            geometry = _as_geometry(aoi)
        except Exception as error:  # noqa: B902  (bad bbox, geocoder failures)
            raise HTTPException(422, f"cannot resolve AOI: {error}") from None
        try:
            url = _resolve_url(geometry, update=False)
        except Exception as error:  # noqa: B902  (ExtractNotFoundError, geocode)
            raise HTTPException(422, f"no covering OSM extract: {error}") from None
        return geometry, url

    @app.post("/api/osm/resolve")
    def osm_resolve(payload: dict = Body(...)):
        aoi = payload.get("aoi")
        if aoi is None:
            raise HTTPException(422, "missing field 'aoi'")
        geometry, url = _resolve_extract(aoi)
        minx, miny, maxx, maxy = geometry.bounds
        return {
            "bbox": [minx, miny, maxx, maxy],
            "url": url,
            "name": _extract_name(url),
        }

    @app.post("/api/osm/download")
    def osm_download(payload: dict = Body(...)):
        url = payload.get("url")
        if not isinstance(url, str) or not url:
            raise HTTPException(422, "'url' must be the confirmed extract URL")
        aoi = _acquire_bbox(payload.get("bbox"))
        crop = payload.get("crop", True)
        discard_edits = payload.get("discard_edits", False)
        if not isinstance(crop, bool) or not isinstance(discard_edits, bool):
            raise HTTPException(422, "'crop' and 'discard_edits' must be booleans")
        with lock:
            if osm_state["dirty"] and not discard_edits:
                raise HTTPException(
                    409, "unsaved network edits; save first or set discard_edits"
                )
            # The confirmed extract must still resolve now, so a place geocoded
            # at resolve time can't download a different one.
            _, resolved_url = _resolve_extract(aoi)
            if resolved_url != url:
                raise HTTPException(409, "extract changed — re-confirm")
            import transitio.osm as osm

            try:
                path = osm.fetch_pbf(aoi, crop=crop)
            except Exception as error:  # noqa: B902  (download/crop failures)
                raise HTTPException(502, f"OSM download failed: {error}") from None
            # Load + guard the candidate before swapping, so a bad download
            # never replaces a working network.
            loaded = _load_network(path)
            osm_state["source"] = os.fspath(path)
            osm_state["editor"] = loaded
            osm_state["dirty"] = False  # a freshly loaded network has no edits
            return {
                "path": os.fspath(path),
                "nodes": int(len(loaded.nodes)),
                "ways": int(len(loaded.ways)),
            }

    _SNAP_TOLERANCE_M = 8.0  # metres: reuse an existing node / accept a split

    def _distance(a, b):
        return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5

    def _aeqd(lon0, lat0):
        from pyproj import Transformer

        return Transformer.from_crs(
            "EPSG:4326",
            f"+proj=aeqd +lat_0={lat0} +lon_0={lon0} +datum=WGS84",
            always_xy=True,
        ).transform

    def _node_nearest(editor):
        # The existing node nearest a point within tolerance (or None). Pure:
        # used to plan connectivity before any mutation.
        from shapely.geometry import Point
        from shapely.strtree import STRtree

        nodes = editor.nodes
        if not len(nodes):  # e.g. every way (and its nodes) was deleted
            return lambda lon, lat: None
        lons = nodes.geometry.x.to_numpy()
        lats = nodes.geometry.y.to_numpy()
        ids = [int(i) for i in nodes["id"]]
        project = _aeqd(float(lons[0]), float(lats[0]))
        xs, ys = project(lons, lats)
        base = [Point(x, y) for x, y in zip(xs, ys)]
        tree = STRtree(base)

        def nearest(lon, lat):
            here = Point(*project(lon, lat))
            index = tree.nearest(here)
            return (
                ids[index] if base[index].distance(here) <= _SNAP_TOLERANCE_M else None
            )

        return nearest

    def _insert_into_way(editor, way_id, node_id, snapped):
        from shapely.geometry import LineString

        members, geometry = _splittable_way(editor, way_id)
        coords = list(geometry.coords)
        segment = min(
            range(len(coords) - 1),
            key=lambda i: LineString([coords[i], coords[i + 1]]).distance(snapped),
        )
        editor.reshape_way(
            way_id, members[: segment + 1] + [node_id] + members[segment + 1 :]
        )

    def _splittable_way(editor, way_id):
        # A way can be split only if it lies fully inside the extract, where
        # its member list maps 1:1 to its geometry.
        row = editor.ways[editor.ways["id"] == way_id]
        if row.empty:
            raise HTTPException(404, f"no way {way_id}")
        members = list(row.iloc[0]["nodes"])
        geometry = row.iloc[0].geometry
        if (
            geometry is None
            or geometry.geom_type != "LineString"
            or len(geometry.coords) != len(members)
        ):
            raise HTTPException(422, f"way {way_id} leaves the extract; cannot split")
        return members, geometry

    def _project_onto_way(geometry, lon, lat):
        # The point on the way nearest the click; refuse if the click is not
        # actually on the way (avoids bending an unrelated way to a stray point).
        from shapely.geometry import Point

        snapped = geometry.interpolate(geometry.project(Point(lon, lat)))
        sx, sy = _aeqd(lon, lat)(snapped.x, snapped.y)
        if (sx * sx + sy * sy) ** 0.5 > _SNAP_TOLERANCE_M:
            raise HTTPException(422, "split point is not on the way")
        return snapped

    def _check_vertex(editor, vertex, node_ids):
        if not isinstance(vertex, dict):
            raise HTTPException(422, "each vertex must be an object")
        if "node" in vertex:
            if _network_int_id(vertex["node"]) not in node_ids:
                raise HTTPException(404, f"no node {vertex['node']}")
        elif "split_way" in vertex:
            lon, lat = _network_lonlat(vertex)
            _, geometry = _splittable_way(editor, _network_int_id(vertex["split_way"]))
            _project_onto_way(geometry, lon, lat)
        else:
            _network_lonlat(vertex)

    @app.post("/api/network/ways")
    def network_add_way(payload: dict = Body(...)):
        vertices = payload.get("vertices")
        if not isinstance(vertices, list) or len(vertices) < 2:
            raise HTTPException(422, "'vertices' needs at least two points")
        tags = _network_tags(payload)
        # An untagged way is unroutable and snapped-over silently; require a
        # tag. The snap network_type, not this check, decides routability.
        if not tags:
            raise HTTPException(422, "a way needs at least one tag")
        with lock:
            editor = get_osm_editor()
            node_ids = {int(value) for value in editor.nodes["id"]}
            for vertex in vertices:
                _check_vertex(editor, vertex, node_ids)
            nearest = _node_nearest(editor)

            # Resolve every vertex to one shared "site" (a single node) without
            # mutating, so a collapsed draw is rejected before anything is
            # created and vertices meeting at a point share one node. A site
            # holds an existing node id or a fresh coordinate, plus the ways the
            # node must be spliced into (a crossing junction or a shared node).
            sites = []
            metric = [None]  # a projection for same-draw proximity

            def near_site(lon, lat):
                if metric[0] is None:
                    metric[0] = _aeqd(lon, lat)
                here = metric[0](lon, lat)
                for index, site in enumerate(sites):
                    if site["coord"] is None:
                        continue
                    if _distance(here, metric[0](*site["coord"])) <= _SNAP_TOLERANCE_M:
                        return index
                return None

            def site_for(existing, coord, way, snapped):
                if existing is not None:
                    index = next(
                        (i for i, s in enumerate(sites) if s["existing"] == existing),
                        None,
                    )
                else:
                    index = near_site(*coord)
                if index is None:
                    sites.append({"existing": existing, "coord": coord, "ways": {}})
                    index = len(sites) - 1
                if way is not None:
                    sites[index]["ways"].setdefault(way, snapped)
                return index

            vertex_sites = []
            for vertex in vertices:
                if "node" in vertex:
                    vertex_sites.append(
                        site_for(_network_int_id(vertex["node"]), None, None, None)
                    )
                elif "split_way" in vertex:
                    way_id = _network_int_id(vertex["split_way"])
                    lon, lat = _network_lonlat(vertex)
                    way_members, geometry = _splittable_way(editor, way_id)
                    snapped = _project_onto_way(geometry, lon, lat)
                    reuse = nearest(snapped.x, snapped.y)
                    if reuse is not None and reuse in way_members:
                        vertex_sites.append(site_for(reuse, None, None, None))
                    elif reuse is not None:  # an existing node shared onto this way
                        vertex_sites.append(site_for(reuse, None, way_id, snapped))
                    else:  # a fresh junction shared by every way meeting here
                        vertex_sites.append(
                            site_for(None, (snapped.x, snapped.y), way_id, snapped)
                        )
                else:
                    lon, lat = _network_lonlat(vertex)
                    hit = nearest(lon, lat)
                    if hit is not None:
                        vertex_sites.append(site_for(hit, None, None, None))
                    else:
                        vertex_sites.append(site_for(None, (lon, lat), None, None))

            collapsed = [vertex_sites[0]]
            for index in vertex_sites[1:]:
                if index != collapsed[-1]:
                    collapsed.append(index)
            if len(collapsed) < 2:
                raise HTTPException(422, "way collapsed to a single node")

            # Apply: create each site's node once, splice it into its ways.
            # Mark dirty up front: the node/reshape mutations below happen
            # before the final add_way, so a mid-apply failure still leaves the
            # network changed.
            osm_state["dirty"] = True
            node_of = {}
            for index in collapsed:
                if index in node_of:
                    continue
                site = sites[index]
                node_of[index] = (
                    site["existing"]
                    if site["existing"] is not None
                    else editor.add_node(*site["coord"])
                )
                for target_way, at in site["ways"].items():
                    _insert_into_way(editor, target_way, node_of[index], at)
            members = [node_of[index] for index in collapsed]
            way_id = _edit_network(lambda: editor.add_way(members, **tags))
        return {"id": way_id}

    @app.patch("/api/network/ways/{way_id}")
    def network_update_way(way_id: str, payload: dict = Body(...)):
        target = _network_int_id(way_id)
        tags = _network_tags(payload)
        if not tags:
            raise HTTPException(422, "no tags to set")
        with lock:
            editor = get_osm_editor()
            _edit_network(lambda: editor.retag_way(target, **tags))
        return {"ok": True}

    @app.delete("/api/network/ways/{way_id}")
    def network_delete_way(way_id: str):
        target = _network_int_id(way_id)
        with lock:
            editor = get_osm_editor()
            _edit_network(lambda: editor.delete_way(target))
        return {"ok": True}

    return app
