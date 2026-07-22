"""The editor's HTTP API over a transitio FeedEditor."""

from __future__ import annotations

import os


def _geojson_feature(geometry_mapping, properties):
    return {"type": "Feature", "geometry": geometry_mapping, "properties": properties}


def create_app(
    editor=None,
    *,
    osm_pbf=None,
    network_type="driving",
    snap_custom_filter=None,
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
        OSM extract enabling ``POST /api/shapes/snap`` (requires the
        ``transitio[snap]`` extra).
    network_type : str, default "driving"
        pyrosm network type for snapping.
    snap_custom_filter : dict, optional
        Default pyrosm Overpass-style tag filter for snapping (e.g.
        ``{"railway": ["tram"]}``); a per-request ``custom_filter``
        overrides it. See :func:`~transitio.edit.snap_to_network`.
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

    import math
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

    def get_catalog():
        if catalog["client"] is None:
            if catalog_factory is not None:
                catalog["client"] = catalog_factory()
            else:
                from transitio.catalog import MobilityDatabase

                catalog["client"] = MobilityDatabase()
        return catalog["client"]

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
                "snapAvailable": osm_pbf is not None,
                "tables": {},
                "currentFeedId": None,
            }
        return {
            "source": entry.source,
            "snapAvailable": osm_pbf is not None,
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
        if osm_pbf is None:
            raise HTTPException(
                409, "no OSM extract configured; start the GUI with an extract"
            )
        from transitio.edit import snap_to_network

        custom_filter = payload.get("custom_filter", snap_custom_filter)
        if custom_filter is not None and not isinstance(custom_filter, dict):
            raise HTTPException(422, "custom_filter must be an object")
        try:
            if custom_filter is not None:
                line = snap_to_network(
                    payload["waypoints"], osm_pbf, custom_filter=custom_filter
                )
            else:
                line = snap_to_network(
                    payload["waypoints"], osm_pbf, network_type=network_type
                )
        except KeyError as error:
            raise HTTPException(422, f"missing field {error}") from None
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
        # No refresh token means search_feeds served the CSV export, which
        # lacks historical datasets and hosted validation reports.
        csv_fallback = not getattr(client, "_refresh_token", None)
        return {
            "feeds": [_feed_result(feed) for feed in feeds],
            "csv_fallback": csv_fallback,
        }

    return app
