"""The editor's HTTP API over a transitio FeedEditor."""

from __future__ import annotations

import os


def _geojson_feature(geometry_mapping, properties):
    return {"type": "Feature", "geometry": geometry_mapping, "properties": properties}


def create_app(editor, *, osm_pbf=None, network_type="driving", allowed_hosts=None):
    """Build the FastAPI app serving one :class:`~transitio.FeedEditor`.

    The app exposes the feed's tables and geometries, mutation endpoints
    mirroring the editor helpers, a snapping endpoint backed by
    :func:`~transitio.edit.snap_to_network` (when ``osm_pbf`` is given),
    and a save endpoint running the validator. It serves everything on
    the loopback interface for a single local user; there is no
    authentication.

    Parameters
    ----------
    editor : FeedEditor or FeedBuilder
        The feed being edited; mutations apply to it in place.
    osm_pbf : str or pathlib.Path, optional
        OSM extract enabling ``POST /api/shapes/snap`` (requires the
        ``transitio[snap]`` extra).
    network_type : str, default "driving"
        pyrosm network type for snapping.
    allowed_hosts : list of str, optional
        Accepted ``Host`` header values (DNS-rebinding guard); defaults
        to the loopback names.

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
    # every touch of the shared editor.
    lock = threading.Lock()

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
        return {
            "source": (os.fspath(editor.source) if hasattr(editor, "source") else None),
            "snapAvailable": osm_pbf is not None,
            "tables": {
                name: len(table) for name, table in sorted(editor.tables.items())
            },
        }

    @app.get("/api/tables/{name}")
    def table(name: str, offset: int = 0, limit: int = 1000):
        with lock:
            return _table(name, offset, limit)

    def _table(name, offset, limit):
        if name not in editor.tables:
            raise HTTPException(404, f"no table {name}")
        frame = editor.tables[name]
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
        try:
            frame = editor.stops
        except ValueError:
            return {"type": "FeatureCollection", "features": []}
        features = []
        for _, row in frame.iterrows():
            geometry = row.geometry
            if geometry is None:
                continue
            properties = {
                key: value for key, value in row.items() if key != frame.geometry.name
            }
            features.append(_geojson_feature(geometry.__geo_interface__, properties))
        return {"type": "FeatureCollection", "features": features}

    @app.get("/api/shapes")
    def shapes_geojson():
        with lock:
            return _shapes_geojson()

    def _shapes_geojson():
        try:
            frame = editor.shapes
        except ValueError:
            return {"type": "FeatureCollection", "features": []}
        features = [
            _geojson_feature(
                row.geometry.__geo_interface__, {"shape_id": row["shape_id"]}
            )
            for _, row in frame.iterrows()
            if row.geometry is not None
        ]
        return {"type": "FeatureCollection", "features": features}

    @app.post("/api/stops")
    def add_stop(payload: dict = Body(...)):
        try:
            with lock:
                editor.add_stop(
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
                editor.update_stop(stop_id, **payload)
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
                editor.add_agency(
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
                editor.add_service(
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
                editor.add_route(
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
                editor.update_route(route_id, **payload)
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
                editor.drop_route(route_id)
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
                editor.add_trip(
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
                editor.shift_trip(trip_id, int(payload["seconds"]))
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
                editor.set_headway(
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
                editor.add_frequency_trip(
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
                editor.add_shape(payload["shape_id"], payload["points"])
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

        try:
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
            return {"routes": _timetable.list_routes(editor)}

    @app.get("/api/routes/{route_id:path}/trips")
    def route_trips(route_id: str):
        from transitio_editor import _timetable

        with lock:
            return {"trips": _timetable.list_trips(editor, route_id)}

    @app.get("/api/trips/{trip_id:path}/times")
    def get_trip_times(trip_id: str):
        from transitio_editor import _timetable

        with lock:
            records = _timetable.trip_times(editor, trip_id)
        if records is None:
            raise HTTPException(404, f"no trip {trip_id}")
        return {"trip_id": trip_id, "times": records}

    @app.put("/api/trips/{trip_id:path}/times")
    def put_trip_times(trip_id: str, payload: dict = Body(...)):
        from transitio_editor import _timetable

        try:
            with lock:
                _timetable.set_trip_times(editor, trip_id, payload["times"])
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
                _timetable.drop_trip(editor, trip_id)
        except LookupError as error:
            raise HTTPException(404, str(error)) from None
        return {"ok": True}

    @app.post("/api/validate")
    def validate(payload: dict = Body(default={})):
        """Validate the current in-memory feed without persisting it."""
        import tempfile

        try:
            with lock, tempfile.TemporaryDirectory() as scratch:
                report = editor.save(
                    os.path.join(scratch, "current.zip"), check=False, **payload
                )
        except (TypeError, ValueError) as error:
            raise HTTPException(422, str(error)) from None
        return {"report": report}

    @app.post("/api/save")
    def save(payload: dict = Body(default={})):
        target = payload.get("path") or (
            os.fspath(editor.source) if hasattr(editor, "source") else None
        )
        if target is None:
            raise HTTPException(422, "no output path: pass {'path': ...}")
        if not str(target).endswith(".zip"):
            raise HTTPException(422, "output path must end in .zip")
        try:
            with lock:
                report = editor.save(target, check=payload.get("check", True))
        except InvalidFeedError as error:
            return {"saved": True, "clean": False, "report": error.report}
        except (TypeError, ValueError) as error:
            raise HTTPException(422, str(error)) from None
        clean = not any(notice["severity"] == "ERROR" for notice in report["notices"])
        return {"saved": True, "clean": clean, "report": report}

    return app
