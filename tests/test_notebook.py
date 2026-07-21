import builtins

import pytest

import transitio._core  # noqa: F401
from transitio.edit import FeedBuilder, FeedEditor  # noqa: E402

from transitio_editor.notebook import (
    _center,
    _feed_geojson,
    feed_map,
    serve,
)  # noqa: E402


def build(tmp_path):
    b = FeedBuilder()
    b.add_agency("hsl", "HSL", "https://hsl.fi", "Europe/Helsinki")
    b.add_stop("s1", "Kamppi", 60.169, 24.931)
    b.add_stop("s2", "Steissi", 60.171, 24.941)
    b.add_route("r1", 0, "1", agency_id="hsl")
    b.add_service("wk", "weekdays", "20260101", "20261231")
    b.add_shape("sh1", [(60.169, 24.931), (60.171, 24.941)])
    b.add_frequency_trip(
        "r1",
        "wk",
        "t1",
        [("s1", 0), ("s2", 300)],
        start="06:00:00",
        end="09:00:00",
        headway=600,
        shape_id="sh1",
    )
    return b


def test_feed_geojson_and_center(tmp_path):
    data = _feed_geojson(build(tmp_path))
    assert len(data["stops"]["features"]) == 2
    assert data["stops"]["features"][0]["geometry"]["type"] == "Point"
    assert data["stops"]["features"][0]["properties"]["stop_id"] == "s1"
    assert "geometry" not in data["stops"]["features"][0]["properties"]
    assert len(data["shapes"]["features"]) == 1
    assert data["shapes"]["features"][0]["properties"]["shape_id"] == "sh1"

    lat, lon = _center(data)
    assert lat == pytest.approx(60.17, abs=0.01)
    assert lon == pytest.approx(24.936, abs=0.01)


def test_feed_geojson_empty_feed():
    data = _feed_geojson(FeedBuilder())
    assert data["stops"]["features"] == []
    assert data["shapes"]["features"] == []
    assert _center(data) == (0.0, 0.0)


def test_feed_map_builder_and_path(tmp_path):
    pytest.importorskip("ipyleaflet")
    import ipyleaflet

    the_map = feed_map(build(tmp_path))
    assert isinstance(the_map, ipyleaflet.Map)
    # base tiles + shapes layer + stops layer
    assert len(the_map.layers) == 3

    source = tmp_path / "feed.zip"
    build(tmp_path).save(source, reference_date="20260601")
    from_path = feed_map(source)
    assert isinstance(from_path, ipyleaflet.Map)


def test_feed_map_without_ipyleaflet(tmp_path, monkeypatch):
    real_import = builtins.__import__

    def no_ipyleaflet(name, *args, **kwargs):
        if name == "ipyleaflet":
            raise ImportError("no ipyleaflet")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", no_ipyleaflet)
    with pytest.raises(ImportError, match=r"transitio-editor\[notebook\]"):
        feed_map(build(tmp_path))


def test_center_handles_antimeridian():
    geojson = {
        "stops": {
            "type": "FeatureCollection",
            "features": [
                {"geometry": {"coordinates": [179.9, 60.0]}},
                {"geometry": {"coordinates": [-179.9, 60.0]}},
            ],
        },
        "shapes": {"type": "FeatureCollection", "features": []},
    }
    lat, lon = _center(geojson)
    assert lat == pytest.approx(60.0)
    assert abs(lon) == pytest.approx(180.0, abs=0.2)  # near ±180, not 0


def test_json_safe_values():
    import numpy as np
    import pandas as pd

    from transitio_editor.notebook import _json_safe

    assert _json_safe("x") == "x"
    assert _json_safe(None) is None
    assert _json_safe(pd.NA) is None
    assert _json_safe(float("inf")) is None
    assert _json_safe(np.int64(5)) == 5
    assert isinstance(_json_safe(np.int64(5)), int)


def test_serve_raises_when_server_does_not_start(tmp_path, monkeypatch):
    pytest.importorskip("IPython")
    import uvicorn

    class DeadServer:
        def __init__(self, config):
            self.started = False

        def run(self):  # exits immediately without binding
            pass

    monkeypatch.setattr(uvicorn, "Server", DeadServer)
    source = tmp_path / "feed.zip"
    build(tmp_path).save(source, reference_date="20260601")
    with pytest.raises(RuntimeError, match="failed to start"):
        serve(FeedEditor(source), port=8413)


def test_serve_returns_iframe(tmp_path, monkeypatch):
    pytest.importorskip("IPython")
    import uvicorn

    class FakeServer:
        def __init__(self, config):
            self.config = config
            self.started = True

        def run(self):
            pass

    monkeypatch.setattr(uvicorn, "Server", FakeServer)

    source = tmp_path / "feed.zip"
    build(tmp_path).save(source, reference_date="20260601")
    frame = serve(FeedEditor(source), port=8412)

    from IPython.display import IFrame

    assert isinstance(frame, IFrame)
    assert "8412" in frame.src
