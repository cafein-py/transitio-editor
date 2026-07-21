"""Jupyter notebook helpers: view a feed on a map, or embed the editor.

``feed_map`` renders a feed's stops and shapes on an ipyleaflet map for
quick inspection; ``serve`` runs the full editor in a background thread
and returns an IFrame embedding it in the notebook. Both accept a
:class:`transitio.FeedEditor`/``FeedBuilder`` or a feed-zip path.

Install the extra: ``pip install transitio-editor[notebook]``.
"""

from __future__ import annotations


def _as_editor(feed):
    if hasattr(feed, "tables"):
        return feed
    from transitio.edit import FeedEditor

    return FeedEditor(feed)


def _feed_geojson(editor):
    """``{"stops": FeatureCollection, "shapes": FeatureCollection}``."""
    stops = {"type": "FeatureCollection", "features": []}
    try:
        frame = editor.stops
    except (ValueError, KeyError):
        frame = None
    if frame is not None:
        name_column = frame.geometry.name
        for _, row in frame.iterrows():
            geometry = row.geometry
            if geometry is None:
                continue
            stops["features"].append(
                {
                    "type": "Feature",
                    "geometry": geometry.__geo_interface__,
                    "properties": {
                        key: value for key, value in row.items() if key != name_column
                    },
                }
            )
    shapes = {"type": "FeatureCollection", "features": []}
    try:
        sframe = editor.shapes
    except (ValueError, KeyError):
        sframe = None
    if sframe is not None:
        for _, row in sframe.iterrows():
            geometry = row.geometry
            if geometry is None:
                continue
            shapes["features"].append(
                {
                    "type": "Feature",
                    "geometry": geometry.__geo_interface__,
                    "properties": {"shape_id": row["shape_id"]},
                }
            )
    return {"stops": stops, "shapes": shapes}


def _center(geojson, fallback=(0.0, 0.0)):
    """Mean (lat, lon) over every feature coordinate, for the map center."""
    lats, lons = [], []

    def walk(coordinates):
        if (
            len(coordinates) == 2
            and isinstance(coordinates[0], (int, float))
            and isinstance(coordinates[1], (int, float))
        ):
            lons.append(coordinates[0])
            lats.append(coordinates[1])
        else:
            for part in coordinates:
                walk(part)

    for collection in (geojson["stops"], geojson["shapes"]):
        for feature in collection["features"]:
            walk(feature["geometry"]["coordinates"])
    if not lats:
        return fallback
    return (sum(lats) / len(lats), sum(lons) / len(lons))


def feed_map(feed, *, zoom=12):
    """An ipyleaflet map of a feed's stops and shapes.

    Parameters
    ----------
    feed : FeedEditor, FeedBuilder or path
        The feed to display.
    zoom : int, default 12
        Initial zoom level.

    Returns
    -------
    ipyleaflet.Map
    """
    try:
        import ipyleaflet
    except ImportError as error:
        raise ImportError(
            "feed_map requires ipyleaflet; install transitio-editor[notebook]"
        ) from error

    data = _feed_geojson(_as_editor(feed))
    the_map = ipyleaflet.Map(center=_center(data), zoom=zoom)
    if data["shapes"]["features"]:
        the_map.add(
            ipyleaflet.GeoJSON(
                data=data["shapes"],
                style={"color": "#35507a", "weight": 3, "opacity": 0.8},
            )
        )
    if data["stops"]["features"]:
        the_map.add(
            ipyleaflet.GeoJSON(
                data=data["stops"],
                point_style={
                    "radius": 5,
                    "color": "#e67e22",
                    "fillColor": "#e67e22",
                    "fillOpacity": 0.8,
                    "weight": 1,
                },
            )
        )
    return the_map


def serve(feed, *, port=8300, osm_pbf=None, height=600, **create_app_kwargs):
    """Run the editor in a background thread and embed it in the notebook.

    Starts the FastAPI editor for ``feed`` on ``127.0.0.1:port`` in a
    daemon thread and returns an ``IPython.display.IFrame`` pointing at
    it. The server lives for the notebook kernel's lifetime.

    Parameters
    ----------
    feed : FeedEditor, FeedBuilder or path
        The feed to edit; edits apply in place and are saved from the UI.
    port : int, default 8300
        Loopback port.
    osm_pbf : str or path, optional
        OSM extract enabling snapped drawing.
    height : int, default 600
        IFrame height in pixels.
    **create_app_kwargs
        Passed to :func:`transitio_editor.create_app` (e.g.
        ``network_type``, ``snap_custom_filter``).

    Returns
    -------
    IPython.display.IFrame
    """
    import threading
    import time

    try:
        import uvicorn
        from IPython.display import IFrame
    except ImportError as error:
        raise ImportError(
            "serve requires uvicorn and IPython; install "
            "transitio-editor[notebook] inside Jupyter"
        ) from error

    from transitio_editor import create_app

    app = create_app(_as_editor(feed), osm_pbf=osm_pbf, **create_app_kwargs)
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(50):  # wait up to ~5 s for the server to bind
        if server.started:
            break
        time.sleep(0.1)
    return IFrame(f"http://127.0.0.1:{port}", width="100%", height=height)
