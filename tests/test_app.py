import pytest

# Hard imports: the editor's CI always installs the full core and
# fastapi, and a broken install must fail the suite, not skip it.
import transitio._core  # noqa: F401
from fastapi.testclient import TestClient  # noqa: E402

from transitio.edit import FeedBuilder, FeedEditor  # noqa: E402
from transitio_editor import create_app  # noqa: E402


@pytest.fixture
def editor(tmp_path):
    builder = FeedBuilder()
    builder.add_agency("hsl", "HSL", "https://hsl.fi", "Europe/Helsinki")
    builder.add_stop("s1", "Kamppi", 60.169, 24.931)
    builder.add_stop("s2", "Steissi", 60.171, 24.941)
    builder.add_route("r1", 0, "1", agency_id="hsl")
    builder.add_service("wk", "weekdays", "20260101", "20261231")
    builder.add_shape("sh1", [(60.169, 24.931), (60.171, 24.941)])
    builder.add_frequency_trip(
        "r1",
        "wk",
        "t1",
        [("s1", 0), ("s2", 300)],
        start="06:00:00",
        end="09:00:00",
        headway=600,
        shape_id="sh1",
    )
    source = tmp_path / "feed.zip"
    builder.save(source, reference_date="20260601")
    return FeedEditor(source)


def test_feed_summary_and_tables(editor):
    client = TestClient(create_app(editor))
    summary = client.get("/api/feed").json()
    assert summary["tables"]["stops.txt"] == 2
    assert summary["source"].endswith("feed.zip")

    table = client.get("/api/tables/stops.txt").json()
    assert table["total"] == 2
    assert table["rows"][0]["stop_id"] == "s1"
    assert client.get("/api/tables/absent.txt").status_code == 404

    window = client.get("/api/tables/stops.txt", params={"offset": 1}).json()
    assert len(window["rows"]) == 1


def test_geojson_endpoints(editor):
    client = TestClient(create_app(editor))
    stops = client.get("/api/stops").json()
    assert stops["type"] == "FeatureCollection"
    assert len(stops["features"]) == 2
    assert stops["features"][0]["geometry"]["type"] == "Point"

    shapes = client.get("/api/shapes").json()
    assert len(shapes["features"]) == 1
    assert shapes["features"][0]["geometry"]["type"] == "LineString"
    assert shapes["features"][0]["properties"]["shape_id"] == "sh1"


def test_mutation_endpoints(editor, tmp_path):
    client = TestClient(create_app(editor))
    ok = client.post(
        "/api/stops",
        json={
            "stop_id": "s3",
            "stop_name": "Uusi",
            "stop_lat": 60.18,
            "stop_lon": 24.95,
        },
    )
    assert ok.status_code == 200
    assert client.post("/api/stops", json={"stop_id": "x"}).status_code == 422

    assert (
        client.patch("/api/stops/s3", json={"stop_name": "Uudempi"}).status_code == 200
    )
    assert client.patch("/api/stops/nope", json={"a": "b"}).status_code == 404

    added = client.post(
        "/api/shapes",
        json={"shape_id": "sh2", "points": [[60.18, 24.95], [60.19, 24.96]]},
    )
    assert added.status_code == 200

    saved = client.post("/api/save", json={"path": str(tmp_path / "out.zip")})
    body = saved.json()
    assert body["saved"] is True and body["clean"] is True
    assert (tmp_path / "out.zip").exists()

    reread = FeedEditor(tmp_path / "out.zip")
    assert "Uudempi" in set(reread.tables["stops.txt"]["stop_name"])
    assert "sh2" in set(reread.tables["shapes.txt"]["shape_id"])


def test_snap_endpoint_requires_extract(editor):
    client = TestClient(create_app(editor))
    response = client.post(
        "/api/shapes/snap",
        json={"waypoints": [[60.169, 24.931], [60.171, 24.941]]},
    )
    assert response.status_code == 409


def test_save_reports_unclean_feed(tmp_path):
    builder = FeedBuilder()
    builder.add_agency("a", "A", "https://a.example", "Europe/Helsinki")
    client = TestClient(create_app(builder))
    saved = client.post("/api/save", json={"path": str(tmp_path / "bad.zip")})
    body = saved.json()
    assert body["saved"] is True and body["clean"] is False
    assert any(n["code"] == "missing_required_file" for n in body["report"]["notices"])


def test_cli_requires_existing_feed(tmp_path):
    from transitio_editor.cli import main

    with pytest.raises(SystemExit):
        main([str(tmp_path / "absent.zip")])


def test_full_builder_surface_over_http(tmp_path):
    client = TestClient(create_app(FeedBuilder()))
    assert (
        client.post(
            "/api/agencies",
            json={
                "agency_id": "a",
                "agency_name": "A",
                "agency_url": "https://a.example",
                "agency_timezone": "Europe/Helsinki",
            },
        ).status_code
        == 200
    )
    assert (
        client.post(
            "/api/services",
            json={
                "service_id": "wk",
                "days": "weekdays",
                "start_date": "20260101",
                "end_date": "20261231",
            },
        ).status_code
        == 200
    )
    for stop_id, lat, lon in (("s1", 60.169, 24.931), ("s2", 60.171, 24.941)):
        client.post(
            "/api/stops",
            json={
                "stop_id": stop_id,
                "stop_name": stop_id,
                "stop_lat": lat,
                "stop_lon": lon,
            },
        )
    client.post(
        "/api/routes",
        json={
            "route_id": "r1",
            "route_type": 3,
            "route_short_name": "1",
            "agency_id": "a",
        },
    )
    assert (
        client.post(
            "/api/trips",
            json={
                "route_id": "r1",
                "service_id": "wk",
                "trip_id": "t1",
                "stops": [
                    ["s1", "08:00:00", "08:00:00"],
                    ["s2", "08:05:00", "08:05:00"],
                ],
            },
        ).status_code
        == 200
    )
    # editor-only operations answer 501 on a bare builder
    assert client.post("/api/trips/t1/shift", json={"seconds": 600}).status_code == 501
    saved = client.post(
        "/api/save",
        json={"path": str(tmp_path / "built.zip"), "check": False},
    ).json()
    assert saved["saved"] is True and saved["clean"] is True

    edit_client = TestClient(create_app(FeedEditor(tmp_path / "built.zip")))
    assert (
        edit_client.post("/api/trips/t1/shift", json={"seconds": 600}).status_code
        == 200
    )
    assert (
        edit_client.patch(
            "/api/routes/r1", json={"route_long_name": "Long"}
        ).status_code
        == 200
    )
    saved = edit_client.post(
        "/api/save", json={"path": str(tmp_path / "edited.zip")}
    ).json()
    assert saved["clean"] is True
    times = FeedEditor(tmp_path / "edited.zip").tables["stop_times.txt"]
    assert list(times["departure_time"]) == ["08:10:00", "08:15:00"]

    assert edit_client.delete("/api/routes/r1").status_code == 200


def test_unclean_save_with_check_false_reports_dirty(tmp_path):
    builder = FeedBuilder()
    builder.add_agency("a", "A", "https://a.example", "Europe/Helsinki")
    client = TestClient(create_app(builder))
    saved = client.post(
        "/api/save",
        json={"path": str(tmp_path / "bad.zip"), "check": False},
    ).json()
    assert saved["saved"] is True and saved["clean"] is False


def test_bad_numeric_payloads_are_422(editor):
    client = TestClient(create_app(editor))
    for lat in ("not-a-number", float("nan"), float("inf")):
        response = client.post(
            "/api/stops",
            json={
                "stop_id": "x",
                "stop_name": "X",
                "stop_lat": str(lat),
                "stop_lon": 24.9,
            },
        )
        assert response.status_code == 422


def test_cli_refuses_non_loopback_host(tmp_path):
    import zipfile as _zipfile

    from transitio_editor.cli import main

    feed = tmp_path / "feed.zip"
    with _zipfile.ZipFile(feed, "w") as archive:
        archive.writestr("agency.txt", "agency_id\n")
    with pytest.raises(SystemExit):
        main([str(feed), "--host", "0.0.0.0"])


def test_host_header_guard_and_zip_target(editor, tmp_path):
    client = TestClient(create_app(editor))
    rebound = client.get("/api/feed", headers={"host": "evil.example"})
    assert rebound.status_code == 400

    bad_target = client.post(
        "/api/save", json={"path": str(tmp_path / "not-a-feed.txt")}
    )
    assert bad_target.status_code == 422


def test_ui_and_static_assets_served(editor):
    client = TestClient(create_app(editor))
    index = client.get("/")
    assert index.status_code == 200
    assert "maplibre-gl.js" in index.text
    assert "app.js" in index.text
    assert "vue.global.prod.js" in index.text
    for asset in (
        "/static/app.js",
        "/static/style.css",
        "/static/vendor/maplibre-gl.js",
        "/static/vendor/maplibre-gl.css",
        "/static/vendor/vue.global.prod.js",
    ):
        assert client.get(asset).status_code == 200

    summary = client.get("/api/feed").json()
    assert summary["snapAvailable"] is False
    with_pbf = TestClient(create_app(editor, osm_pbf="fake.osm.pbf"))
    assert with_pbf.get("/api/feed").json()["snapAvailable"] is True


def test_foreign_origin_posts_are_refused(editor, tmp_path):
    client = TestClient(create_app(editor))
    refused = client.post(
        "/api/save",
        json={"path": str(tmp_path / "out.zip")},
        headers={"origin": "https://evil.example"},
    )
    assert refused.status_code == 403

    other_port = client.post(
        "/api/save",
        json={"path": str(tmp_path / "out.zip")},
        headers={"origin": "http://127.0.0.1:9999"},
    )
    assert other_port.status_code == 403  # other localhost ports are foreign

    allowed = client.post(
        "/api/save",
        json={"path": str(tmp_path / "out.zip")},
        headers={"origin": "http://testserver"},
    )
    assert allowed.status_code == 200
    # reads are unaffected by foreign origins (responses stay unreadable
    # cross-origin anyway)
    assert (
        client.get("/api/feed", headers={"origin": "https://evil.example"}).status_code
        == 200
    )


def test_validate_endpoint_without_saving(editor, tmp_path):
    client = TestClient(create_app(editor))
    body = client.post("/api/validate", json={"reference_date": "20260601"}).json()
    assert not any(n["severity"] == "ERROR" for n in body["report"]["notices"])

    broken = TestClient(create_app(FeedBuilder()))
    body = broken.post("/api/validate", json={}).json()
    assert any(n["code"] == "missing_required_file" for n in body["report"]["notices"])
    assert client.post("/api/validate", json={"bogus_kwarg": 1}).status_code == 422


def test_ids_with_slashes_route_correctly(tmp_path):
    builder = FeedBuilder()
    builder.add_agency("a", "A", "https://a.example", "Europe/Helsinki")
    builder.add_stop("HSL/1234", "Slashy", 60.17, 24.94)
    source = tmp_path / "feed.zip"
    builder.save(source, check=False)
    client = TestClient(create_app(FeedEditor(source)))
    ok = client.patch("/api/stops/HSL%2F1234", json={"stop_name": "Renamed"})
    assert ok.status_code == 200
    table = client.get("/api/tables/stops.txt").json()
    assert table["rows"][0]["stop_name"] == "Renamed"
