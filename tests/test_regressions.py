"""One test per fixed defect."""

import pandas as pd
import pytest

import transitio._core  # noqa: F401
from fastapi.testclient import TestClient  # noqa: E402

from transitio.edit import FeedBuilder, FeedEditor  # noqa: E402
from transitio_editor import create_app  # noqa: E402


@pytest.fixture
def degenerate_feed(tmp_path):
    """A feed with a coordinate-less stop and a single-point shape.

    Both are legal enough to load and appear in real feeds; neither can
    become a geometry.
    """
    builder = FeedBuilder()
    builder.add_agency("a", "A", "https://a.example", "Europe/Helsinki")
    builder.add_stop("s1", "Placed", 60.169, 24.931)
    builder.add_stop("s2", "Nowhere", "", "")
    builder.add_route("r1", 3, "1", agency_id="a")
    builder.add_service("wk", "weekdays", "20260101", "20261231")
    builder.add_shape("good", [(60.169, 24.931), (60.171, 24.941)])
    builder.add_trip(
        "r1",
        "wk",
        "t1",
        [("s1", "08:00:00", "08:00:00"), ("s2", "08:05:00", "08:05:00")],
        shape_id="good",
    )
    # a shape with one point: no LineString, so no geometry
    stub = pd.DataFrame(
        [
            {
                "shape_id": "stub",
                "shape_pt_lat": "60.17",
                "shape_pt_lon": "24.93",
                "shape_pt_sequence": "1",
                "shape_dist_traveled": "0.0",
            }
        ]
    )
    builder.tables["shapes.txt"] = pd.concat(
        [builder.tables["shapes.txt"], stub], ignore_index=True
    ).fillna("")
    path = tmp_path / "degenerate.zip"
    builder.save(path, check=False)
    return FeedEditor(path)


def test_missing_geometries_do_not_break_the_geojson_endpoints(degenerate_feed):
    # A missing geometry reads back from iterrows() as NaN (not None) with
    # geopandas 1.x, which used to raise AttributeError and 500 the request.
    client = TestClient(create_app(degenerate_feed))

    stops = client.get("/api/stops")
    assert stops.status_code == 200
    assert [f["properties"]["stop_id"] for f in stops.json()["features"]] == ["s1"]

    shapes = client.get("/api/shapes")
    assert shapes.status_code == 200
    assert [f["properties"]["shape_id"] for f in shapes.json()["features"]] == ["good"]
