"""The editor's HTTP API over a transitio FeedEditor."""

from __future__ import annotations

import math
import os


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


def _network_features(frame):
    """A GeoJSON FeatureCollection of an OsmEditor nodes/ways frame."""
    geometry_name = frame.geometry.name
    features = []
    for _, row in frame.iterrows():
        geometry = row[geometry_name]
        if geometry is None:
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
    max_network_ways=50000,
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
    max_network_ways : int, default 50000
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
                f"{max_network_ways} limit (raise --max-network-ways)",
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
        number = float(value)
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
            }
        return {
            "source": entry.source,
            "snapAvailable": osm_state["source"] is not None,
            "tables": {
                name: len(table) for name, table in sorted(entry.editor.tables.items())
            },
            "currentFeedId": entry.feed_id,
        }

    @app.get("/api/tables/{name}")
    def table(name: str, offset: int = 0, limit: int = 1000):
        with lock:
            return _table(name, offset, limit)

    def _table(name, offset, limit):
        if name not in current_editor().tables:
            raise HTTPException(404, f"no table {name}")
        frame = current_editor().tables[name]
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
                if geometry is None:
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
            for _, row in frame.iterrows():
                if row.geometry is None:
                    continue
                features.append(
                    _geojson_feature(
                        row.geometry.__geo_interface__,
                        {
                            "shape_id": row["shape_id"],
                            "feed_id": entry.feed_id,
                            "feed_color": entry.color,
                        },
                    )
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
                    os.path.join(scratch, "current.zip"), check=False, **payload
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
                return {"saved": True, "clean": False, "report": error.report}
            except (TypeError, ValueError) as error:
                raise HTTPException(422, str(error)) from None
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
            }

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
        with lock:
            entry = registry.add(
                loaded,
                payload.get("name") or default_name(loaded),
                source=os.fspath(path),
            )
            return entry_dict(entry, registry)

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
            if "active" in payload:
                active = payload["active"]
                if not isinstance(active, bool):
                    raise HTTPException(422, "'active' must be a boolean")
                entry.active = active
            if "name" in payload:
                entry.name = str(payload["name"])
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

    @app.get("/api/search")
    def search(
        country: str | None = None,
        subdivision: str | None = None,
        municipality: str | None = None,
        bbox: str | None = None,
        official: bool = False,
        limit: int = 50,
    ):
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
        return {
            "feeds": [_feed_result(feed) for feed in feeds],
            "csv_fallback": csv_fallback,
        }

    @app.post("/api/catalogue/download")
    def catalogue_download(payload: dict = Body(...)):
        feed_id = payload.get("feed_id")
        if not isinstance(feed_id, str):
            raise HTTPException(422, "'feed_id' must be a string")
        activate = payload.get("activate", True)
        if not isinstance(activate, bool):
            raise HTTPException(422, "'activate' must be a boolean")
        feed = search_cache.get(feed_id)
        if feed is None:
            raise HTTPException(404, f"unknown feed {feed_id}; search for it first")
        if not feed.latest_dataset_url:
            raise HTTPException(422, f"feed {feed_id} has no downloadable dataset")

        from transitio.edit import FeedEditor

        # Download and load outside the lock; only the registry insert needs it.
        try:
            path = get_catalog().download_latest(feed)
            loaded = FeedEditor(path)
        except Exception as error:  # noqa: B902
            raise HTTPException(502, f"download failed: {error}") from None
        with lock:
            entry = registry.add(
                loaded,
                feed.provider or feed.id,
                source=os.fspath(path),
            )
            entry.active = activate
            return entry_dict(entry, registry)

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
        return {"available": osm_state["source"] is not None}

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
