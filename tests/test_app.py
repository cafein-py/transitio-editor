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


def test_snap_endpoint_forwards_custom_filter(editor, monkeypatch):
    from shapely.geometry import LineString

    calls = {}

    def fake_snap(waypoints, pbf, **kwargs):
        calls["waypoints"] = waypoints
        calls["kwargs"] = kwargs
        return LineString([(24.9, 60.1), (24.91, 60.11)])

    monkeypatch.setattr("transitio.edit.snap_to_network", fake_snap)

    client = TestClient(create_app(editor, osm_pbf="fake.osm.pbf"))
    wp = [[60.169, 24.931], [60.171, 24.941]]

    ok = client.post("/api/shapes/snap", json={"waypoints": wp})
    assert ok.status_code == 200
    assert ok.json()["geometry"]["type"] == "LineString"
    assert calls["kwargs"] == {"network_type": "driving"}

    client.post(
        "/api/shapes/snap",
        json={"waypoints": wp, "custom_filter": {"railway": ["tram"]}},
    )
    assert calls["kwargs"] == {"custom_filter": {"railway": ["tram"]}}

    bad = client.post(
        "/api/shapes/snap", json={"waypoints": wp, "custom_filter": "tram"}
    )
    assert bad.status_code == 422


def test_snap_server_default_filter(editor, monkeypatch):
    from shapely.geometry import LineString

    calls = {}

    def fake_snap(waypoints, pbf, **kwargs):
        calls.update(kwargs)
        return LineString([(24.9, 60.1), (24.91, 60.11)])

    monkeypatch.setattr("transitio.edit.snap_to_network", fake_snap)
    client = TestClient(
        create_app(
            editor,
            osm_pbf="fake.osm.pbf",
            snap_custom_filter={"railway": ["tram"]},
        )
    )
    client.post(
        "/api/shapes/snap",
        json={"waypoints": [[60.169, 24.931], [60.171, 24.941]]},
    )
    assert calls == {"custom_filter": {"railway": ["tram"]}}


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


def test_cli_rejects_bad_snap_filter(tmp_path):
    import zipfile as _zipfile

    from transitio_editor.cli import main

    feed = tmp_path / "feed.zip"
    with _zipfile.ZipFile(feed, "w") as archive:
        archive.writestr("agency.txt", "agency_id\n")
    with pytest.raises(SystemExit):
        main([str(feed), "--snap-filter", "not json"])
    with pytest.raises(SystemExit):
        main([str(feed), "--snap-filter", "[1, 2]"])  # not an object


def test_host_header_guard_and_zip_target(editor, tmp_path):
    client = TestClient(create_app(editor))
    rebound = client.get("/api/feed", headers={"host": "evil.example"})
    assert rebound.status_code == 400

    bad_target = client.post(
        "/api/save", json={"path": str(tmp_path / "not-a-feed.txt")}
    )
    assert bad_target.status_code == 422


def test_ui_and_static_assets_served(editor):
    import re

    client = TestClient(create_app(editor))
    index = client.get("/")
    assert index.status_code == 200
    assert '<div id="app">' in index.text

    # The built index references hashed JS/CSS bundles under /static/;
    # every referenced asset must serve.
    assets = re.findall(r'(?:src|href)="(/static/assets/[^"]+)"', index.text)
    assert assets, "built index has no /static/assets references"
    assert any(a.endswith(".js") for a in assets)
    assert any(a.endswith(".css") for a in assets)
    for asset in assets:
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


def test_timetable_endpoints(editor, tmp_path):
    client = TestClient(create_app(editor))
    routes = client.get("/api/routes").json()["routes"]
    assert routes[0]["route_id"] == "r1"

    trips = client.get("/api/routes/r1/trips").json()["trips"]
    assert trips[0]["trip_id"] == "t1"
    assert trips[0]["stop_count"] == 2
    assert trips[0]["frequency_windows"][0]["headway_secs"] == "600"

    detail = client.get("/api/trips/t1/times").json()
    assert [row["stop_id"] for row in detail["times"]] == ["s1", "s2"]
    assert detail["times"][0]["stop_name"] == "Kamppi"

    updated = client.put(
        "/api/trips/t1/times",
        json={
            "times": {"2": {"arrival_time": "6:07:30", "departure_time": "06:08:00"}}
        },
    )
    assert updated.status_code == 200
    detail = client.get("/api/trips/t1/times").json()
    assert detail["times"][1]["arrival_time"] == "06:07:30"
    assert detail["times"][1]["departure_time"] == "06:08:00"

    assert (
        client.put(
            "/api/trips/t1/times",
            json={"times": {"9": {"arrival_time": "06:00:00"}}},
        ).status_code
        == 422
    )
    assert (
        client.put(
            "/api/trips/t1/times",
            json={"times": {"1": {"arrival_time": "6:70:00"}}},
        ).status_code
        == 422
    )
    assert client.get("/api/trips/absent/times").status_code == 404

    assert client.delete("/api/trips/t1").status_code == 200
    assert client.delete("/api/trips/t1").status_code == 404
    table = client.get("/api/tables/stop_times.txt").json()
    assert table["total"] == 0
    frequencies = client.get("/api/tables/frequencies.txt").json()
    assert frequencies["total"] == 0


def test_trip_time_updates_are_atomic_and_blankable(editor):
    client = TestClient(create_app(editor))
    response = client.put(
        "/api/trips/t1/times",
        json={
            "times": {
                "1": {"arrival_time": "07:00:00"},
                "2": {"arrival_time": "7:99:00"},
            }
        },
    )
    assert response.status_code == 422
    detail = client.get("/api/trips/t1/times").json()
    assert detail["times"][0]["arrival_time"] == "06:00:00"  # unchanged

    cleared = client.put(
        "/api/trips/t1/times",
        json={"times": {"2": {"arrival_time": ""}}},
    )
    assert cleared.status_code == 200
    detail = client.get("/api/trips/t1/times").json()
    assert detail["times"][1]["arrival_time"] == ""


def test_drop_trip_cascades_trip_references(editor):
    editor._append(
        "transfers.txt",
        {
            "from_stop_id": "",
            "to_stop_id": "",
            "from_trip_id": "t1",
            "to_trip_id": "",
            "transfer_type": "1",
        },
    )
    editor._append(
        "attributions.txt",
        {
            "attribution_id": "a1",
            "trip_id": "t1",
            "organization_name": "Org",
            "is_producer": "1",
        },
    )
    client = TestClient(create_app(editor))
    assert client.delete("/api/trips/t1").status_code == 200
    assert client.get("/api/tables/transfers.txt").json()["total"] == 0
    assert client.get("/api/tables/attributions.txt").json()["total"] == 0


def _write_feed(path, stop_id, lat, lon):
    b = FeedBuilder()
    b.add_agency("a", "A", "https://a.example", "Europe/Helsinki")
    b.add_stop(stop_id, stop_id, lat, lon)
    b.add_route("r", 3, "1", agency_id="a")
    b.add_service("wk", "weekdays", "20260101", "20261231")
    b.add_trip(
        "t",
        "wk",
        "t1",
        [(stop_id, "08:00:00", "08:00:00"), (stop_id, "08:05:00", "08:05:00")],
    )
    b.save(path, check=False)
    return path


def test_catalogue_single_feed_default(editor):
    client = TestClient(create_app(editor))
    body = client.get("/api/catalogue").json()
    assert len(body["feeds"]) == 1
    only = body["feeds"][0]
    assert only["current"] is True and only["active"] is True
    assert only["color"].startswith("#")
    assert body["current"] == only["feed_id"]


def test_catalogue_add_activate_and_overlay(editor, tmp_path):
    client = TestClient(create_app(editor))
    other = _write_feed(tmp_path / "other.zip", "z9", 60.30, 25.10)

    added = client.post("/api/catalogue", json={"path": str(other), "name": "Metro"})
    assert added.status_code == 200
    entry = added.json()
    assert entry["name"] == "Metro"
    assert entry["current"] is False  # first feed stays current

    feeds = client.get("/api/catalogue").json()["feeds"]
    assert len(feeds) == 2
    # both active -> stops aggregate across feeds, each tagged with feed_id
    stops = client.get("/api/stops").json()["features"]
    feed_ids = {f["properties"]["feed_id"] for f in stops}
    assert feed_ids == {feeds[0]["feed_id"], feeds[1]["feed_id"]}
    assert all("feed_color" in f["properties"] for f in stops)

    # deactivate the second feed -> only the first feed's stops show
    client.patch(f"/api/catalogue/{entry['feed_id']}", json={"active": False})
    stops = client.get("/api/stops").json()["features"]
    assert {f["properties"]["feed_id"] for f in stops} == {feeds[0]["feed_id"]}


def test_catalogue_set_current_scopes_mutations(editor, tmp_path):
    client = TestClient(create_app(editor))
    other = _write_feed(tmp_path / "other.zip", "z9", 60.30, 25.10)
    entry = client.post("/api/catalogue", json={"path": str(other)}).json()

    # current is still the first feed; add a stop -> goes to first feed
    client.post(
        "/api/stops",
        json={"stop_id": "new1", "stop_name": "N1", "stop_lat": 60.2, "stop_lon": 24.9},
    )
    # switch current to the second feed; the summary follows
    assert (
        client.put(
            "/api/catalogue/current", json={"feed_id": entry["feed_id"]}
        ).status_code
        == 200
    )
    summary = client.get("/api/feed").json()
    assert summary["currentFeedId"] == entry["feed_id"]
    assert "new1" not in {
        r["stop_id"] for r in client.get("/api/tables/stops.txt").json()["rows"]
    }

    assert (
        client.put("/api/catalogue/current", json={"feed_id": "nope"}).status_code
        == 404
    )


def test_catalogue_remove_reassigns_current(editor, tmp_path):
    client = TestClient(create_app(editor))
    entry = client.post(
        "/api/catalogue",
        json={"path": str(_write_feed(tmp_path / "b.zip", "z", 60.3, 25.1))},
    ).json()
    feeds = client.get("/api/catalogue").json()
    first = feeds["current"]

    removed = client.delete(f"/api/catalogue/{first}")
    assert removed.status_code == 200
    assert removed.json()["current"] == entry["feed_id"]  # reassigned
    assert client.delete("/api/catalogue/first").status_code == 404


def test_catalogue_add_errors(editor, tmp_path):
    client = TestClient(create_app(editor))
    assert client.post("/api/catalogue", json={}).status_code == 422
    assert (
        client.post(
            "/api/catalogue", json={"path": str(tmp_path / "absent.zip")}
        ).status_code
        == 404
    )
    bad = tmp_path / "bad.zip"
    bad.write_bytes(b"not a zip")
    assert client.post("/api/catalogue", json={"path": str(bad)}).status_code == 422


def test_catalogue_rejects_malformed_inputs(editor):
    client = TestClient(create_app(editor))
    assert client.post("/api/catalogue", json={"path": ["a", "b"]}).status_code == 422
    assert client.post("/api/catalogue", json={"path": None}).status_code == 422
    assert client.put("/api/catalogue/current", json={"feed_id": 5}).status_code == 422
    feed_id = client.get("/api/catalogue").json()["feeds"][0]["feed_id"]
    assert (
        client.patch(f"/api/catalogue/{feed_id}", json={"active": "false"}).status_code
        == 422
    )  # not silently truthy


def test_no_feed_loaded_returns_409(tmp_path):
    client = TestClient(create_app())  # empty registry
    assert client.get("/api/feed").json()["currentFeedId"] is None
    assert client.get("/api/catalogue").json()["feeds"] == []
    assert (
        client.post(
            "/api/stops",
            json={"stop_id": "s", "stop_name": "S", "stop_lat": 60.1, "stop_lon": 24.9},
        ).status_code
        == 409
    )


class _StubCatalog:
    """Stands in for MobilityDatabase so search tests avoid the network."""

    def __init__(self, feeds, *, token=None, error=None, download_path=None):
        self._refresh_token = token
        self._feeds = feeds
        self._error = error
        self._download_path = download_path
        self.calls = []
        self.downloaded = []

    def search_feeds(self, **kwargs):
        self.calls.append(kwargs)
        if self._error is not None:
            raise self._error
        return self._feeds

    def download_latest(self, feed, directory=None):
        self.downloaded.append(feed.id)
        if self._download_path is None:
            raise RuntimeError("download unavailable")
        return self._download_path


def _catalog_feed(feed_id="mdb-1", *, downloadable=True):
    from transitio.catalog import Feed

    return Feed.from_api(
        {
            "id": feed_id,
            "provider": "HSL",
            "status": "active",
            "is_official": True,
            "source_info": {
                "producer_url": "https://p.example",
                "license_url": "https://l.example",
            },
            "locations": [
                {
                    "country_code": "FI",
                    "subdivision_name": "Uusimaa",
                    "municipality": "Helsinki",
                }
            ],
            "latest_dataset": (
                {"hosted_url": "https://d.example/latest.zip"} if downloadable else {}
            ),
        }
    )


def test_search_returns_serialized_feeds(editor):
    stub = _StubCatalog([_catalog_feed()], token="tok")
    client = TestClient(create_app(editor, catalog_factory=lambda: stub))
    body = client.get("/api/search", params={"municipality": "Helsinki"}).json()
    assert body["csv_fallback"] is False
    (feed,) = body["feeds"]
    assert feed["id"] == "mdb-1"
    assert feed["provider"] == "HSL"
    assert feed["locations"] == [
        {"country": "FI", "subdivision": "Uusimaa", "municipality": "Helsinki"}
    ]
    assert feed["official"] is True
    assert feed["downloadable"] is True
    assert feed["license_url"] == "https://l.example"
    assert stub.calls[0]["municipality"] == "Helsinki"
    assert stub.calls[0]["limit"] == 50


def test_search_csv_fallback_when_no_token(editor):
    stub = _StubCatalog([], token=None)
    client = TestClient(create_app(editor, catalog_factory=lambda: stub))
    body = client.get("/api/search").json()
    assert body["csv_fallback"] is True
    assert body["feeds"] == []


def test_search_forwards_bbox_and_filters(editor):
    stub = _StubCatalog([], token="tok")
    client = TestClient(create_app(editor, catalog_factory=lambda: stub))
    response = client.get(
        "/api/search",
        params={
            "bbox": "24.9,60.1,25.1,60.3",
            "official": "true",
            "country": "FI",
            "limit": "10",
        },
    )
    assert response.status_code == 200
    call = stub.calls[0]
    assert call["aoi"] == (24.9, 60.1, 25.1, 60.3)
    assert call["official_only"] is True
    assert call["country_code"] == "FI"
    assert call["limit"] == 10


def test_search_rejects_malformed_bbox(editor):
    stub = _StubCatalog([], token="tok")
    client = TestClient(create_app(editor, catalog_factory=lambda: stub))
    for bbox in (
        "1,2,3",  # wrong arity
        "a,b,c,d",  # not numbers
        "nan,0,1,1",  # non-finite
        "0,0,inf,1",  # non-finite
        "2,0,1,1",  # reversed longitude
        "0,0,1,100",  # latitude out of range
    ):
        assert client.get("/api/search", params={"bbox": bbox}).status_code == 422, bbox
    assert stub.calls == []  # never reached the client


def test_search_error_returns_502(editor):
    stub = _StubCatalog([], token="tok", error=RuntimeError("boom"))
    client = TestClient(create_app(editor, catalog_factory=lambda: stub))
    assert client.get("/api/search").status_code == 502


def test_download_adds_searched_feed_to_catalogue(editor, tmp_path):
    zip_path = _write_feed(tmp_path / "dl.zip", "d1", 60.4, 25.2)
    stub = _StubCatalog([_catalog_feed()], token="tok", download_path=zip_path)
    client = TestClient(create_app(editor, catalog_factory=lambda: stub))

    client.get("/api/search")  # populates the download cache
    added = client.post("/api/catalogue/download", json={"feed_id": "mdb-1"})
    assert added.status_code == 200
    entry = added.json()
    assert entry["name"] == "HSL" and entry["active"] is True
    assert stub.downloaded == ["mdb-1"]

    feeds = client.get("/api/catalogue").json()["feeds"]
    assert len(feeds) == 2
    assert any(f["source"].endswith("dl.zip") for f in feeds)
    # the downloaded feed shows on the map (active) alongside the first
    stops = client.get("/api/stops").json()["features"]
    assert entry["feed_id"] in {f["properties"]["feed_id"] for f in stops}


def test_download_activate_false_loads_hidden(editor, tmp_path):
    zip_path = _write_feed(tmp_path / "dl.zip", "d1", 60.4, 25.2)
    stub = _StubCatalog([_catalog_feed()], token="tok", download_path=zip_path)
    client = TestClient(create_app(editor, catalog_factory=lambda: stub))
    client.get("/api/search")
    entry = client.post(
        "/api/catalogue/download", json={"feed_id": "mdb-1", "activate": False}
    ).json()
    assert entry["active"] is False


def test_download_unknown_feed_404(editor):
    stub = _StubCatalog([], token="tok")
    client = TestClient(create_app(editor, catalog_factory=lambda: stub))
    assert (
        client.post("/api/catalogue/download", json={"feed_id": "ghost"}).status_code
        == 404
    )


def test_download_rejects_malformed(editor):
    stub = _StubCatalog([_catalog_feed()], token="tok")
    client = TestClient(create_app(editor, catalog_factory=lambda: stub))
    assert (
        client.post("/api/catalogue/download", json={"feed_id": 5}).status_code == 422
    )
    assert (
        client.post(
            "/api/catalogue/download", json={"feed_id": "mdb-1", "activate": "yes"}
        ).status_code
        == 422
    )


def test_download_not_downloadable_422(editor):
    stub = _StubCatalog([_catalog_feed(downloadable=False)], token="tok")
    client = TestClient(create_app(editor, catalog_factory=lambda: stub))
    client.get("/api/search")
    assert (
        client.post("/api/catalogue/download", json={"feed_id": "mdb-1"}).status_code
        == 422
    )


def test_download_failure_returns_502(editor):
    stub = _StubCatalog([_catalog_feed()], token="tok", download_path=None)
    client = TestClient(create_app(editor, catalog_factory=lambda: stub))
    client.get("/api/search")
    assert (
        client.post("/api/catalogue/download", json={"feed_id": "mdb-1"}).status_code
        == 502
    )


def _osm_pbf():
    pytest.importorskip("pyrosm")
    from pyrosm import get_data

    return get_data("test_pbf")


def test_network_available_flag(editor):
    assert TestClient(create_app(editor)).get("/api/network").json() == {
        "available": False
    }
    with_pbf = TestClient(create_app(editor, osm_pbf="fake.osm.pbf")).get(
        "/api/network"
    )
    assert with_pbf.json() == {"available": True}


def test_network_nodes_and_ways_geojson(editor):
    client = TestClient(create_app(editor, osm_pbf=_osm_pbf(), network_type="driving"))

    nodes = client.get("/api/network/nodes").json()
    assert nodes["type"] == "FeatureCollection" and len(nodes["features"]) > 0
    node = nodes["features"][0]
    assert node["geometry"]["type"] == "Point" and "id" in node["properties"]

    ways = client.get("/api/network/ways").json()
    assert len(ways["features"]) > 0
    way = ways["features"][0]
    assert way["geometry"]["type"] in ("LineString", "MultiLineString")
    assert "id" in way["properties"] and "nodes" in way["properties"]


def test_network_not_loaded_returns_409(editor):
    client = TestClient(create_app(editor))  # no osm_pbf
    assert client.get("/api/network/nodes").status_code == 409
    assert client.get("/api/network/ways").status_code == 409


def test_network_size_guard_returns_413(editor):
    client = TestClient(
        create_app(
            editor, osm_pbf=_osm_pbf(), network_type="driving", max_network_ways=1
        )
    )
    assert client.get("/api/network/ways").status_code == 413


def test_network_add_and_delete_node(editor):
    client = TestClient(create_app(editor, osm_pbf=_osm_pbf(), network_type="driving"))
    added = client.post(
        "/api/network/nodes",
        json={"lon": 26.94, "lat": 60.52, "tags": {"barrier": "gate"}},
    )
    assert added.status_code == 200
    node_id = added.json()["id"]
    assert node_id < 0  # provisional negative id

    def node_ids():
        features = client.get("/api/network/nodes").json()["features"]
        return {f["properties"]["id"] for f in features}

    assert node_id in node_ids()
    assert client.delete(f"/api/network/nodes/{node_id}").status_code == 200
    assert node_id not in node_ids()


def _first_network_node(client):
    return client.get("/api/network/nodes").json()["features"][0]["properties"]["id"]


def test_network_move_node(editor):
    client = TestClient(create_app(editor, osm_pbf=_osm_pbf(), network_type="driving"))
    node_id = _first_network_node(client)
    assert (
        client.patch(
            f"/api/network/nodes/{node_id}", json={"lon": 26.9401, "lat": 60.5201}
        ).status_code
        == 200
    )
    moved = next(
        f
        for f in client.get("/api/network/nodes").json()["features"]
        if f["properties"]["id"] == node_id
    )
    lon, lat = moved["geometry"]["coordinates"]
    assert abs(lon - 26.9401) < 1e-6 and abs(lat - 60.5201) < 1e-6


def test_network_retag_node(editor):
    client = TestClient(create_app(editor, osm_pbf=_osm_pbf(), network_type="driving"))
    node_id = _first_network_node(client)
    assert (
        client.patch(
            f"/api/network/nodes/{node_id}", json={"tags": {"highway": "crossing"}}
        ).status_code
        == 200
    )
    feature = next(
        f
        for f in client.get("/api/network/nodes").json()["features"]
        if f["properties"]["id"] == node_id
    )
    assert feature["properties"].get("highway") == "crossing"


def test_network_reset_discards_edits(editor):
    client = TestClient(create_app(editor, osm_pbf=_osm_pbf(), network_type="driving"))
    node_id = client.post(
        "/api/network/nodes", json={"lon": 26.94, "lat": 60.52}
    ).json()["id"]
    assert client.post("/api/network/reset").status_code == 200
    features = client.get("/api/network/nodes").json()["features"]
    assert node_id not in {f["properties"]["id"] for f in features}


def test_network_node_errors(editor):
    client = TestClient(create_app(editor, osm_pbf=_osm_pbf(), network_type="driving"))
    assert client.delete("/api/network/nodes/999999999").status_code == 404
    assert (
        client.patch(
            "/api/network/nodes/999999999", json={"lon": 26.9, "lat": 60.5}
        ).status_code
        == 404
    )
    assert client.patch("/api/network/nodes/nope", json={"tags": {}}).status_code == 422
    node_id = _first_network_node(client)
    assert (
        client.patch(
            f"/api/network/nodes/{node_id}", json={"tags": {"id": "5"}}
        ).status_code
        == 422  # reserved column rejected
    )


def test_network_node_validation(editor):
    client = TestClient(create_app(editor, osm_pbf=_osm_pbf(), network_type="driving"))
    # malformed / missing coordinates are 422, not 500
    assert client.post("/api/network/nodes", json={"lat": 60.5}).status_code == 422
    assert (
        client.post("/api/network/nodes", json={"lon": "x", "lat": 60.5}).status_code
        == 422
    )
    # a falsey non-object 'tags' is rejected, not silently dropped
    assert (
        client.post(
            "/api/network/nodes", json={"lon": 26.9, "lat": 60.5, "tags": []}
        ).status_code
        == 422
    )
    node_id = _first_network_node(client)
    # a one-sided coordinate is rejected
    assert (
        client.patch(f"/api/network/nodes/{node_id}", json={"lon": 26.9}).status_code
        == 422
    )
    # a valid move combined with an invalid tag is atomic: the node stays put
    before = next(
        f
        for f in client.get("/api/network/nodes").json()["features"]
        if f["properties"]["id"] == node_id
    )
    response = client.patch(
        f"/api/network/nodes/{node_id}",
        json={"lon": 26.9999, "lat": 60.5999, "tags": {"id": "5"}},
    )
    assert response.status_code == 422
    after = next(
        f
        for f in client.get("/api/network/nodes").json()["features"]
        if f["properties"]["id"] == node_id
    )
    assert after["geometry"]["coordinates"] == before["geometry"]["coordinates"]


def test_network_coord_range_and_tag_values(editor):
    client = TestClient(create_app(editor, osm_pbf=_osm_pbf(), network_type="driving"))
    # out-of-range coordinates are rejected
    assert (
        client.post("/api/network/nodes", json={"lon": 999, "lat": 60.5}).status_code
        == 422
    )
    assert (
        client.post("/api/network/nodes", json={"lon": 26.9, "lat": 120}).status_code
        == 422
    )
    # a non-string tag value is rejected (no "None"/repr coercion)
    assert (
        client.post(
            "/api/network/nodes", json={"lon": 26.9, "lat": 60.5, "tags": {"k": None}}
        ).status_code
        == 422
    )


def test_network_features_snapshot(editor):
    client = TestClient(create_app(editor, osm_pbf=_osm_pbf(), network_type="driving"))
    body = client.get("/api/network/features").json()
    assert body["nodes"]["type"] == "FeatureCollection"
    assert body["ways"]["type"] == "FeatureCollection"
    assert len(body["nodes"]["features"]) > 0 and len(body["ways"]["features"]) > 0


def test_network_huge_int_coord_is_422(editor):
    client = TestClient(create_app(editor, osm_pbf=_osm_pbf(), network_type="driving"))
    # a legal JSON integer beyond float range must not 500
    assert (
        client.post(
            "/api/network/nodes", json={"lon": 10**400, "lat": 60.5}
        ).status_code
        == 422
    )


def _network_ways(client):
    features = client.get("/api/network/features").json()["ways"]["features"]
    return {w["properties"]["id"]: w for w in features}


def test_network_add_way_from_coords(editor):
    client = TestClient(create_app(editor, osm_pbf=_osm_pbf(), network_type="driving"))
    new = client.post(
        "/api/network/ways",
        json={
            "vertices": [{"lon": 26.95, "lat": 60.52}, {"lon": 26.951, "lat": 60.521}],
            "tags": {"highway": "path"},
        },
    )
    assert new.status_code == 200
    way_id = new.json()["id"]
    assert way_id < 0
    ways = _network_ways(client)
    assert way_id in ways and ways[way_id]["properties"].get("highway") == "path"
    assert len(ways[way_id]["properties"]["nodes"]) == 2  # two fresh nodes


def test_network_add_way_reuses_clicked_node(editor):
    client = TestClient(create_app(editor, osm_pbf=_osm_pbf(), network_type="driving"))
    node_id = _first_network_node(client)
    new = client.post(
        "/api/network/ways",
        json={
            "vertices": [{"node": node_id}, {"lon": 26.95, "lat": 60.52}],
            "tags": {"highway": "footway"},
        },
    )
    assert new.status_code == 200
    ways = _network_ways(client)
    assert node_id in ways[new.json()["id"]]["properties"]["nodes"]


def test_network_add_way_splits_existing_way(editor):
    client = TestClient(create_app(editor, osm_pbf=_osm_pbf(), network_type="driving"))
    ways = client.get("/api/network/features").json()["ways"]["features"]
    # a way fully inside the extract (coords map 1:1 to members) can be split
    target = next(
        w
        for w in ways
        if w["geometry"]["type"] == "LineString"
        and len(w["geometry"]["coordinates"]) == len(w["properties"]["nodes"])
        and len(w["properties"]["nodes"]) >= 2
    )
    way_id = target["properties"]["id"]
    before = list(target["properties"]["nodes"])
    (x0, y0), (x1, y1) = target["geometry"]["coordinates"][:2]
    mid_lon, mid_lat = (x0 + x1) / 2, (y0 + y1) / 2
    new = client.post(
        "/api/network/ways",
        json={
            "vertices": [
                {"split_way": way_id, "lon": mid_lon, "lat": mid_lat},
                {"lon": mid_lon + 0.001, "lat": mid_lat + 0.001},
            ],
            "tags": {"highway": "footway"},
        },
    )
    assert new.status_code == 200
    ways2 = _network_ways(client)
    after = list(ways2[way_id]["properties"]["nodes"])
    assert len(after) == len(before) + 1  # junction inserted
    (junction,) = set(after) - set(before)
    assert junction in ways2[new.json()["id"]]["properties"]["nodes"]  # connected


def test_network_delete_and_retag_way(editor):
    client = TestClient(create_app(editor, osm_pbf=_osm_pbf(), network_type="driving"))
    way_id = next(iter(_network_ways(client)))
    assert (
        client.patch(
            f"/api/network/ways/{way_id}", json={"tags": {"surface": "gravel"}}
        ).status_code
        == 200
    )
    assert _network_ways(client)[way_id]["properties"].get("surface") == "gravel"
    assert client.delete(f"/api/network/ways/{way_id}").status_code == 200
    assert way_id not in _network_ways(client)


def test_network_way_errors(editor):
    client = TestClient(create_app(editor, osm_pbf=_osm_pbf(), network_type="driving"))
    assert (
        client.post(
            "/api/network/ways", json={"vertices": [{"lon": 26.9, "lat": 60.5}]}
        ).status_code
        == 422  # fewer than two vertices
    )
    assert (
        client.post(
            "/api/network/ways",
            json={
                "vertices": [{"node": 999999999}, {"lon": 26.9, "lat": 60.5}],
                "tags": {"highway": "footway"},
            },
        ).status_code
        == 404  # unknown node reference
    )
    assert client.delete("/api/network/ways/999999999").status_code == 404
    assert (
        client.patch(
            "/api/network/ways/999999999", json={"tags": {"a": "b"}}
        ).status_code
        == 404
    )
    way_id = next(iter(_network_ways(client)))
    assert client.patch(f"/api/network/ways/{way_id}", json={}).status_code == 422


def test_network_add_way_snaps_coord_to_nearby_node(editor):
    client = TestClient(create_app(editor, osm_pbf=_osm_pbf(), network_type="driving"))
    features = client.get("/api/network/features").json()
    node = features["nodes"]["features"][0]
    node_id = node["properties"]["id"]
    nlon, nlat = node["geometry"]["coordinates"]
    before_nodes = len(features["nodes"]["features"])
    # first vertex ~0.3 m from an existing node -> reuse it, not duplicate
    new = client.post(
        "/api/network/ways",
        json={
            "vertices": [
                {"lon": nlon + 0.000005, "lat": nlat},
                {"lon": nlon + 0.001, "lat": nlat},
            ],
            "tags": {"highway": "footway"},
        },
    )
    assert new.status_code == 200
    members = _network_ways(client)[new.json()["id"]]["properties"]["nodes"]
    assert node_id in members  # snapped to the existing node
    after_nodes = len(client.get("/api/network/features").json()["nodes"]["features"])
    assert after_nodes == before_nodes + 1  # only the far endpoint is new


def test_network_split_far_point_rejected(editor):
    client = TestClient(create_app(editor, osm_pbf=_osm_pbf(), network_type="driving"))
    target = next(
        w
        for w in client.get("/api/network/features").json()["ways"]["features"]
        if w["geometry"]["type"] == "LineString"
        and len(w["geometry"]["coordinates"]) == len(w["properties"]["nodes"])
    )
    new = client.post(
        "/api/network/ways",
        json={
            "vertices": [
                {"split_way": target["properties"]["id"], "lon": 10.0, "lat": 10.0},
                {"lon": 10.001, "lat": 10.0},
            ],
            "tags": {"highway": "footway"},
        },
    )
    assert new.status_code == 422  # the point is not on the way


def test_network_id_parsing_rejects_non_integers(editor):
    client = TestClient(create_app(editor, osm_pbf=_osm_pbf(), network_type="driving"))
    tail = {"lon": 26.9, "lat": 60.5}
    tags = {"highway": "footway"}
    assert (
        client.post(
            "/api/network/ways",
            json={"vertices": [{"node": 123.9}, tail], "tags": tags},
        ).status_code
        == 422  # float id not truncated
    )
    assert (
        client.post(
            "/api/network/ways",
            json={"vertices": [{"node": True}, tail], "tags": tags},
        ).status_code
        == 422  # bool id not coerced
    )


def test_network_way_reserved_tag_key_rejected_atomically(editor):
    client = TestClient(create_app(editor, osm_pbf=_osm_pbf(), network_type="driving"))
    before = len(client.get("/api/network/features").json()["nodes"]["features"])
    # a reserved tag key (collides with a method parameter) is rejected up
    # front — 422, not a 500, and with no orphan nodes created
    response = client.post(
        "/api/network/ways",
        json={
            "vertices": [{"lon": 26.95, "lat": 60.52}, {"lon": 26.951, "lat": 60.521}],
            "tags": {"lon": "5"},
        },
    )
    assert response.status_code == 422
    after = len(client.get("/api/network/features").json()["nodes"]["features"])
    assert after == before  # nothing was created


def test_network_split_at_existing_member_reuses_node(editor):
    client = TestClient(create_app(editor, osm_pbf=_osm_pbf(), network_type="driving"))
    target = next(
        w
        for w in client.get("/api/network/features").json()["ways"]["features"]
        if w["geometry"]["type"] == "LineString"
        and len(w["geometry"]["coordinates"]) == len(w["properties"]["nodes"])
        and len(w["properties"]["nodes"]) >= 3
    )
    way_id = target["properties"]["id"]
    members_before = list(target["properties"]["nodes"])
    before_nodes = len(client.get("/api/network/features").json()["nodes"]["features"])
    # split exactly at an existing interior member node
    vx, vy = target["geometry"]["coordinates"][1]
    new = client.post(
        "/api/network/ways",
        json={
            "vertices": [
                {"split_way": way_id, "lon": vx, "lat": vy},
                {"lon": vx + 0.001, "lat": vy},
            ],
            "tags": {"highway": "footway"},
        },
    )
    assert new.status_code == 200
    ways = _network_ways(client)
    # the way is unchanged (the existing member was reused, no junction added)
    assert len(ways[way_id]["properties"]["nodes"]) == len(members_before)
    assert members_before[1] in ways[new.json()["id"]]["properties"]["nodes"]
    after_nodes = len(client.get("/api/network/features").json()["nodes"]["features"])
    assert after_nodes == before_nodes + 1  # only the far endpoint is new


def test_network_add_way_nearby_fresh_points_reuse(editor):
    client = TestClient(create_app(editor, osm_pbf=_osm_pbf(), network_type="driving"))
    # two drawn points within snap tolerance resolve to one node, so the way
    # collapses (422) instead of creating colocated nodes and a zero-length edge
    response = client.post(
        "/api/network/ways",
        json={
            "vertices": [
                {"lon": 26.9500, "lat": 60.5200},
                {"lon": 26.950001, "lat": 60.5200},
            ],
            "tags": {"highway": "footway"},
        },
    )
    assert response.status_code == 422


def test_network_tag_and_coord_edge_validation(editor):
    client = TestClient(create_app(editor, osm_pbf=_osm_pbf(), network_type="driving"))
    tail = {"lon": 26.91, "lat": 60.5}
    # a tag key colliding with the method receiver is rejected, not a 500
    assert (
        client.post(
            "/api/network/ways",
            json={
                "vertices": [{"lon": 26.9, "lat": 60.5}, tail],
                "tags": {"self": "x"},
            },
        ).status_code
        == 422
    )
    # a boolean coordinate must not pass as 1.0
    assert (
        client.post("/api/network/nodes", json={"lon": True, "lat": 60.5}).status_code
        == 422
    )
    # an explicit null 'tags' is malformed, not treated as absent
    assert (
        client.post(
            "/api/network/nodes", json={"lon": 26.9, "lat": 60.5, "tags": None}
        ).status_code
        == 422
    )
    # exponent-notation id strings are not accepted
    assert (
        client.post(
            "/api/network/ways", json={"vertices": [{"node": "1e3"}, tail]}
        ).status_code
        == 422
    )


def test_network_save_writes_readable_pbf(editor, tmp_path):
    client = TestClient(create_app(editor, osm_pbf=_osm_pbf(), network_type="driving"))
    out = tmp_path / "edited.osm.pbf"
    response = client.post("/api/network/save", json={"path": str(out)})
    assert response.status_code == 200 and response.json()["saved"] is True
    assert out.exists()
    from pyrosm import OSM

    _, edges = OSM(str(out)).get_network("all", nodes=True)
    assert len(edges) > 0  # a re-readable network


def test_network_save_reflects_edits(editor, tmp_path):
    client = TestClient(create_app(editor, osm_pbf=_osm_pbf(), network_type="driving"))
    way_id = client.post(
        "/api/network/ways",
        json={
            "vertices": [{"lon": 26.94, "lat": 60.52}, {"lon": 26.941, "lat": 60.521}],
            "tags": {"highway": "footway"},
        },
    ).json()["id"]
    out = tmp_path / "edited.osm.pbf"
    client.post("/api/network/save", json={"path": str(out)})
    from pyrosm import OSM

    _, edges = OSM(str(out), keep_node_info=True).get_network("all", nodes=True)
    assert way_id in set(edges["id"])  # the drawn way persisted


def test_network_save_errors(editor):
    client = TestClient(create_app(editor, osm_pbf=_osm_pbf(), network_type="driving"))
    assert client.post("/api/network/save", json={}).status_code == 422
    assert client.post("/api/network/save", json={"path": ""}).status_code == 422
    no_network = TestClient(create_app(editor))  # no --osm-pbf
    assert (
        no_network.post("/api/network/save", json={"path": "/tmp/x.pbf"}).status_code
        == 409
    )


def test_snap_routes_through_edited_network(editor):
    pytest.importorskip("networkx")
    client = TestClient(create_app(editor, osm_pbf=_osm_pbf(), network_type="driving"))
    # loading the network makes snapping go through the OsmEditor
    nodes = client.get("/api/network/features").json()["nodes"]["features"]
    a = nodes[0]["geometry"]["coordinates"]
    b = nodes[5]["geometry"]["coordinates"]
    snap = client.post(
        "/api/shapes/snap", json={"waypoints": [[a[1], a[0]], [b[1], b[0]]]}
    )
    assert snap.status_code == 200
    assert snap.json()["geometry"]["type"] == "LineString"


def test_network_add_way_collapse_is_atomic(editor):
    client = TestClient(create_app(editor, osm_pbf=_osm_pbf(), network_type="driving"))
    before = len(client.get("/api/network/features").json()["nodes"]["features"])
    response = client.post(
        "/api/network/ways",
        json={
            "vertices": [
                {"lon": 26.9500, "lat": 60.5200},
                {"lon": 26.950001, "lat": 60.5200},
            ]
        },
    )
    assert response.status_code == 422
    after = len(client.get("/api/network/features").json()["nodes"]["features"])
    assert after == before  # nothing created before the collapse was detected


def test_network_add_railway_way(editor):
    client = TestClient(create_app(editor, osm_pbf=_osm_pbf(), network_type="driving"))
    new = client.post(
        "/api/network/ways",
        json={
            "vertices": [{"lon": 26.94, "lat": 60.52}, {"lon": 26.941, "lat": 60.521}],
            "tags": {"railway": "tram"},  # not a highway
        },
    )
    assert new.status_code == 200
    assert (
        _network_ways(client)[new.json()["id"]]["properties"].get("railway") == "tram"
    )


def test_network_save_refuses_source_and_bad_suffix(editor, tmp_path):
    pbf = _osm_pbf()
    client = TestClient(create_app(editor, osm_pbf=pbf, network_type="driving"))
    assert client.post("/api/network/save", json={"path": str(pbf)}).status_code == 422
    assert (
        client.post(
            "/api/network/save", json={"path": str(tmp_path / "x.txt")}
        ).status_code
        == 422
    )


def test_network_save_writes_provenance(editor, tmp_path):
    import json

    client = TestClient(create_app(editor, osm_pbf=_osm_pbf(), network_type="driving"))
    client.post(
        "/api/network/ways",
        json={
            "vertices": [{"lon": 26.95, "lat": 60.52}, {"lon": 26.951, "lat": 60.521}],
            "tags": {"highway": "path"},
        },
    )
    out = tmp_path / "edited.osm.pbf"
    client.post("/api/network/save", json={"path": str(out)})
    sidecar = tmp_path / "edited.osm.pbf.provenance.json"
    assert sidecar.exists()
    data = json.loads(sidecar.read_text())
    assert data["source"] and data["saved_at"]
    assert data["added_ways"] == 1 and data["added_nodes"] == 2


def test_network_add_way_rejects_untagged(editor):
    client = TestClient(create_app(editor, osm_pbf=_osm_pbf(), network_type="driving"))
    body = {"vertices": [{"lon": 26.95, "lat": 60.52}, {"lon": 26.951, "lat": 60.521}]}
    assert client.post("/api/network/ways", json=body).status_code == 422
    assert (
        client.post("/api/network/ways", json={**body, "tags": {}}).status_code == 422
    )


def test_network_save_sidecar_does_not_follow_symlink(editor, tmp_path):
    import json

    client = TestClient(create_app(editor, osm_pbf=_osm_pbf(), network_type="driving"))
    victim = tmp_path / "victim.txt"
    victim.write_text("keep me")
    out = tmp_path / "edited.osm.pbf"
    sidecar = tmp_path / "edited.osm.pbf.provenance.json"
    sidecar.symlink_to(victim)  # a pre-existing sidecar symlink
    client.post("/api/network/save", json={"path": str(out)})
    assert victim.read_text() == "keep me"  # target untouched
    assert not sidecar.is_symlink()  # replaced, not followed
    assert json.loads(sidecar.read_text())["source"]


def test_network_split_two_ways_at_one_point_keeps_both(editor):
    # drawing across a crossing must split both ways, not collapse to one.
    client = TestClient(create_app(editor, osm_pbf=_osm_pbf(), network_type="driving"))
    client.get("/api/network/features")  # load the network
    w1 = client.post(
        "/api/network/ways",
        json={
            "vertices": [{"lon": 26.95, "lat": 60.52}, {"lon": 26.952, "lat": 60.52}],
            "tags": {"highway": "service"},
        },
    ).json()["id"]
    w2 = client.post(
        "/api/network/ways",
        json={
            "vertices": [
                {"lon": 26.951, "lat": 60.519},
                {"lon": 26.951, "lat": 60.521},
            ],
            "tags": {"highway": "service"},
        },
    ).json()["id"]
    ways = _network_ways(client)
    before1, before2 = ways[w1], ways[w2]
    n1 = len(before1["properties"]["nodes"])
    n2 = len(before2["properties"]["nodes"])
    cross = {"lon": 26.951, "lat": 60.52}  # where w1 and w2 cross
    # a path that passes through the crossing, clicking both ways there
    drawn = client.post(
        "/api/network/ways",
        json={
            "vertices": [
                {"lon": 26.9505, "lat": 60.5205},
                {"split_way": w1, **cross},
                {"split_way": w2, **cross},
                {"lon": 26.9515, "lat": 60.5195},
            ],
            "tags": {"highway": "footway"},
        },
    )
    assert drawn.status_code == 200
    ways = _network_ways(client)
    w1_nodes = ways[w1]["properties"]["nodes"]
    w2_nodes = ways[w2]["properties"]["nodes"]
    assert len(w1_nodes) == n1 + 1  # w1 got a junction
    assert len(w2_nodes) == n2 + 1  # w2 got one too
    # the crossing is a single shared node, not colocated duplicates
    (junction,) = set(w1_nodes) - set(before1["properties"]["nodes"])
    assert junction in w2_nodes
    assert junction in ways[drawn.json()["id"]]["properties"]["nodes"]


def test_network_share_existing_node_across_two_ways(editor):
    # one existing node clicked on two crossing ways must be spliced into both.
    client = TestClient(create_app(editor, osm_pbf=_osm_pbf(), network_type="driving"))
    client.get("/api/network/features")  # load the network
    shared = client.post(
        "/api/network/nodes", json={"lon": 26.951, "lat": 60.52, "tags": {}}
    ).json()["id"]
    w1 = client.post(
        "/api/network/ways",
        json={
            "vertices": [{"lon": 26.95, "lat": 60.52}, {"lon": 26.952, "lat": 60.52}],
            "tags": {"highway": "service"},
        },
    ).json()["id"]
    w2 = client.post(
        "/api/network/ways",
        json={
            "vertices": [
                {"lon": 26.951, "lat": 60.519},
                {"lon": 26.951, "lat": 60.521},
            ],
            "tags": {"highway": "service"},
        },
    ).json()["id"]
    at = {"lon": 26.951, "lat": 60.52}  # projects onto both ways, near `shared`
    drawn = client.post(
        "/api/network/ways",
        json={
            "vertices": [
                {"lon": 26.9505, "lat": 60.5205},
                {"split_way": w1, **at},
                {"split_way": w2, **at},
                {"lon": 26.9515, "lat": 60.5195},
            ],
            "tags": {"highway": "footway"},
        },
    )
    assert drawn.status_code == 200
    ways = _network_ways(client)
    assert shared in ways[w1]["properties"]["nodes"]  # spliced into w1
    assert shared in ways[w2]["properties"]["nodes"]  # and into w2, not just w1


def test_network_save_rejects_nul_byte_path(editor):
    client = TestClient(create_app(editor, osm_pbf=_osm_pbf(), network_type="driving"))
    got = client.post("/api/network/save", json={"path": "x" + chr(0) + ".pbf"})
    assert got.status_code == 422  # not an unhandled 500


def test_snap_reflects_a_new_way(editor):
    pytest.importorskip("networkx")
    client = TestClient(create_app(editor, osm_pbf=_osm_pbf(), network_type="driving"))
    features = client.get("/api/network/features").json()  # load the network
    # attach a new driving way to an existing network node so it joins the
    # routable graph; its far end is a brand-new node absent from the source.
    anchor = features["nodes"]["features"][0]["properties"]["id"]
    a_lon, a_lat = features["nodes"]["features"][0]["geometry"]["coordinates"]
    b_lon, b_lat = a_lon, a_lat + 0.001  # ~110 m away, a fresh node
    client.post(
        "/api/network/ways",
        json={
            "vertices": [{"node": anchor}, {"lon": b_lon, "lat": b_lat}],
            "tags": {"highway": "residential"},
        },
    )
    snap = client.post(
        "/api/shapes/snap",
        json={"waypoints": [[a_lat, a_lon], [b_lat, b_lon]]},
    )
    assert snap.status_code == 200
    coords = snap.json()["geometry"]["coordinates"]  # [lon, lat]
    # reaching the brand-new far node is only possible along the drawn way,
    # i.e. against the edited network materialised for the snap.
    assert abs(coords[-1][0] - b_lon) < 1e-6 and abs(coords[-1][1] - b_lat) < 1e-6


_HELSINKI_BBOX = [24.9, 60.1, 25.0, 60.2]  # covered by the bundled extract index


def test_osm_resolve_returns_extract(editor):
    # resolution uses pyrosm's bundled index — no network needed.
    client = TestClient(create_app(editor))
    got = client.post("/api/osm/resolve", json={"aoi": _HELSINKI_BBOX})
    assert got.status_code == 200
    body = got.json()
    assert body["url"].endswith(".osm.pbf") and body["name"]
    assert len(body["bbox"]) == 4
    assert client.post("/api/osm/resolve", json={}).status_code == 422
    assert client.post("/api/osm/resolve", json={"aoi": [1, 2, 3]}).status_code == 422


def _resolved(client):
    return client.post("/api/osm/resolve", json={"aoi": _HELSINKI_BBOX}).json()


def test_osm_download_sets_network_from_nothing(editor, monkeypatch):
    # an app started without --osm-pbf gains a network via acquisition.
    monkeypatch.setattr("transitio.osm.fetch_pbf", lambda aoi, *, crop=True: _osm_pbf())
    client = TestClient(create_app(editor))  # no osm_pbf
    assert client.get("/api/network").json() == {"available": False}
    r = _resolved(client)
    got = client.post("/api/osm/download", json={"bbox": r["bbox"], "url": r["url"]})
    assert got.status_code == 200 and got.json()["ways"] > 0
    assert client.get("/api/network").json() == {"available": True}
    assert len(client.get("/api/network/features").json()["ways"]["features"]) > 0


def test_osm_download_url_mismatch_409(editor, monkeypatch):
    monkeypatch.setattr("transitio.osm.fetch_pbf", lambda aoi, *, crop=True: _osm_pbf())
    client = TestClient(create_app(editor))
    r = _resolved(client)
    got = client.post(
        "/api/osm/download", json={"bbox": r["bbox"], "url": "https://wrong/x.osm.pbf"}
    )
    assert got.status_code == 409  # extract changed — re-confirm


def test_osm_download_rejects_dirty_network(editor, monkeypatch):
    monkeypatch.setattr("transitio.osm.fetch_pbf", lambda aoi, *, crop=True: _osm_pbf())
    client = TestClient(create_app(editor, osm_pbf=_osm_pbf(), network_type="driving"))
    client.post(  # make the loaded network dirty
        "/api/network/nodes", json={"lon": 26.94, "lat": 60.52, "tags": {}}
    )
    r = _resolved(client)
    blocked = client.post(
        "/api/osm/download", json={"bbox": r["bbox"], "url": r["url"]}
    )
    assert blocked.status_code == 409  # unsaved edits
    ok = client.post(
        "/api/osm/download",
        json={"bbox": r["bbox"], "url": r["url"], "discard_edits": True},
    )
    assert ok.status_code == 200


def test_osm_download_retains_previous_on_failure(editor, monkeypatch):
    client = TestClient(create_app(editor, osm_pbf=_osm_pbf(), network_type="driving"))
    before = len(client.get("/api/network/features").json()["ways"]["features"])

    def boom(aoi, *, crop=True):
        raise RuntimeError("network down")

    monkeypatch.setattr("transitio.osm.fetch_pbf", boom)
    r = _resolved(client)
    got = client.post("/api/osm/download", json={"bbox": r["bbox"], "url": r["url"]})
    assert got.status_code == 502
    # the working network is untouched
    after = len(client.get("/api/network/features").json()["ways"]["features"])
    assert after == before


def test_osm_download_blocks_on_in_place_edit(editor, tmp_path, monkeypatch):
    # a move/retag of an existing element leaves no provisional id or deletion,
    # yet must still block acquisition; saving clears it.
    monkeypatch.setattr("transitio.osm.fetch_pbf", lambda aoi, *, crop=True: _osm_pbf())
    client = TestClient(create_app(editor, osm_pbf=_osm_pbf(), network_type="driving"))
    node_id = _first_network_node(client)
    client.patch(f"/api/network/nodes/{node_id}", json={"lon": 26.9401, "lat": 60.5201})
    r = _resolved(client)
    blocked = client.post(
        "/api/osm/download", json={"bbox": r["bbox"], "url": r["url"]}
    )
    assert blocked.status_code == 409
    out = tmp_path / "saved.osm.pbf"
    assert client.post("/api/network/save", json={"path": str(out)}).status_code == 200
    ok = client.post("/api/osm/download", json={"bbox": r["bbox"], "url": r["url"]})
    assert ok.status_code == 200  # dirty cleared by the save


def _helsinki_pbf():
    pytest.importorskip("pyrosm")
    from pyrosm import get_data

    return get_data("helsinki_pbf")  # ~2.5k ways, larger than test_pbf


def test_osm_download_rejects_oversized_candidate(editor, monkeypatch):
    # the small extract loads under the cap; a larger candidate is rejected and
    # the working network stays intact and usable.
    client = TestClient(
        create_app(
            editor,
            osm_pbf=_osm_pbf(),
            network_type="driving",
            max_network_ways=1000,
        )
    )
    before = len(client.get("/api/network/features").json()["ways"]["features"])
    monkeypatch.setattr(
        "transitio.osm.fetch_pbf", lambda aoi, *, crop=True: _helsinki_pbf()
    )
    r = _resolved(client)
    got = client.post("/api/osm/download", json={"bbox": r["bbox"], "url": r["url"]})
    assert got.status_code == 413
    after = len(client.get("/api/network/features").json()["ways"]["features"])
    assert after == before  # previous network intact


def test_osm_download_rejects_non_bool_flags(editor):
    client = TestClient(create_app(editor))
    r = _resolved(client)
    got = client.post(
        "/api/osm/download",
        json={"bbox": r["bbox"], "url": r["url"], "discard_edits": "false"},
    )
    assert got.status_code == 422  # a truthy string must not bypass the guard


def test_osm_download_rejects_bad_bbox(editor):
    client = TestClient(create_app(editor))
    bad_boxes = [
        [True, 60.1, 25.0, 60.2],  # boolean coordinate
        [24.9, 60.1, 24.9, 60.2],  # zero area
        [24.9, 60.1, 400.0, 60.2],  # longitude out of range
        [10**400, 60.1, 25.0, 60.2],  # overflows float
    ]
    for bad in bad_boxes:
        got = client.post(
            "/api/osm/download", json={"bbox": bad, "url": "https://x/a.osm.pbf"}
        )
        assert got.status_code == 422, bad


def test_osm_download_load_failure_retains_previous(editor, monkeypatch):
    # a candidate that downloads but fails to load must not replace the network.
    client = TestClient(create_app(editor, osm_pbf=_osm_pbf(), network_type="driving"))
    before = len(client.get("/api/network/features").json()["ways"]["features"])
    monkeypatch.setattr(
        "transitio.osm.fetch_pbf", lambda aoi, *, crop=True: "/no/such/file.osm.pbf"
    )
    r = _resolved(client)
    got = client.post("/api/osm/download", json={"bbox": r["bbox"], "url": r["url"]})
    assert got.status_code == 422  # candidate cannot load
    after = len(client.get("/api/network/features").json()["ways"]["features"])
    assert after == before  # previous network intact
