import os

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


def test_cli_starts_without_feed(monkeypatch):
    # no positional feed: the editor opens on an empty builder.
    import uvicorn

    from transitio_editor.cli import main

    served = {}
    monkeypatch.setattr(uvicorn, "run", lambda app, **kw: served.update(app=app))
    # --no-browser: uvicorn is stubbed here, so nothing would ever answer
    assert main(["--no-browser"]) == 0
    client = TestClient(served["app"])
    summary = client.get("/api/feed").json()
    assert summary["source"] is None and summary["tables"] == {}
    # the empty builder is editable from the GUI
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


def test_cli_opens_the_browser(monkeypatch):
    import uvicorn

    from transitio_editor import cli

    opened = []
    monkeypatch.setattr(uvicorn, "run", lambda app, **kw: None)
    monkeypatch.setattr(
        cli, "open_when_serving", lambda url, host, port, token: opened.append(url)
    )
    assert cli.main([]) == 0
    assert opened == ["http://127.0.0.1:8300"]

    # ...unless the user asked it not to
    opened.clear()
    assert cli.main(["--no-browser"]) == 0
    assert opened == []


def test_wildcard_bind_accepts_the_loopback_url_it_opens(monkeypatch):
    import uvicorn

    from transitio_editor import cli

    served = {}
    monkeypatch.setattr(uvicorn, "run", lambda app, **kw: served.update(app=app))
    monkeypatch.setattr(cli, "open_when_serving", lambda *a, **kw: None)
    assert cli.main(["--allow-remote", "--host", "0.0.0.0"]) == 0

    client = TestClient(served["app"])
    # the browser is pointed at loopback, so the host guard must accept it
    assert cli.browser_url("0.0.0.0", 8300) == "http://127.0.0.1:8300"
    for host in ("127.0.0.1:8300", "localhost:8300", "0.0.0.0:8300"):
        assert client.get("/api/feed", headers={"host": host}).status_code == 200
    # a foreign name is still refused
    assert client.get("/api/feed", headers={"host": "evil.example"}).status_code == 400


def test_cli_rejects_a_port_the_url_cannot_name():
    from transitio_editor.cli import main

    for port in ("0", "70000", "-1"):
        with pytest.raises(SystemExit):
            main(["--no-browser", "--port", port])


def test_browser_url_is_reachable_for_every_bind():
    from transitio_editor.cli import browser_url

    assert browser_url("127.0.0.1", 8300) == "http://127.0.0.1:8300"
    # a wildcard bind is not an address a browser can open, in any spelling
    assert browser_url("0.0.0.0", 8300) == "http://127.0.0.1:8300"
    assert browser_url("::", 8300) == "http://[::1]:8300"
    assert browser_url("0:0:0:0:0:0:0:0", 8300) == "http://[::1]:8300"
    assert browser_url("::1", 9000) == "http://[::1]:9000"  # bracketed
    assert browser_url("192.168.1.5", 8300) == "http://192.168.1.5:8300"


def _serve_json(bodies, delay=0.0):
    """A throwaway HTTP server answering the given path -> JSON bodies."""
    import http.server
    import json
    import threading
    import time

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            if self.path in bodies:
                payload = json.dumps(bodies[self.path]).encode()
                self.send_response(200)
                self.send_header("content-type", "application/json")
                self.end_headers()
                self.wfile.write(payload)
            else:
                self.send_response(404)
                self.end_headers()

        def log_message(self, *args):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]

    def run():
        time.sleep(delay)
        server.serve_forever(poll_interval=0.05)

    threading.Thread(target=run, daemon=True).start()
    return server, port


def test_browser_opens_only_once_this_editor_answers(monkeypatch):
    from transitio_editor import cli

    opened = []
    monkeypatch.setattr(cli.webbrowser, "open", opened.append)
    # the API only starts answering after a delay: the browser waits
    server, port = _serve_json({"/api/boot-token": {"token": "tok-1"}}, delay=0.3)
    try:
        cli.open_when_serving(
            f"http://127.0.0.1:{port}", "127.0.0.1", port, "tok-1"
        ).join()
        assert opened == [f"http://127.0.0.1:{port}"]
    finally:
        server.shutdown()


def test_browser_ignores_another_service_on_the_port(monkeypatch):
    from transitio_editor import cli

    opened = []
    monkeypatch.setattr(cli.webbrowser, "open", opened.append)
    # another editor instance already owns the port: it answers the same
    # endpoint, but with its own token — opening a browser onto it would
    # show someone else's session while this launch fails to bind
    server, port = _serve_json({"/api/boot-token": {"token": "someone-else"}})
    try:
        cli.open_when_serving(
            f"http://127.0.0.1:{port}", "127.0.0.1", port, "tok-1", timeout=0.4
        ).join()
        assert opened == []
    finally:
        server.shutdown()

    # non-object JSON on the endpoint must not crash the poller either
    weird, weird_port = _serve_json({"/api/boot-token": None})
    try:
        cli.open_when_serving(
            f"http://127.0.0.1:{weird_port}",
            "127.0.0.1",
            weird_port,
            "tok-1",
            timeout=0.4,
        ).join()
        assert opened == []
    finally:
        weird.shutdown()

    # a catch-all server without the endpoint is ignored the same way
    other, other_port = _serve_json({"/": {"hello": "web"}})
    try:
        cli.open_when_serving(
            f"http://127.0.0.1:{other_port}",
            "127.0.0.1",
            other_port,
            "tok-1",
            timeout=0.4,
        ).join()
        assert opened == []
    finally:
        other.shutdown()


def test_browser_gives_up_quietly_when_nothing_serves(monkeypatch):
    import socket

    from transitio_editor import cli

    opened = []
    monkeypatch.setattr(cli.webbrowser, "open", opened.append, raising=False)
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    # the server never comes up: no browser, no exception, no hang
    cli.open_when_serving(
        "http://127.0.0.1:1", "127.0.0.1", port, "tok-1", timeout=0.3
    ).join()
    assert opened == []


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


def test_catalogue_merge_combines_live_editors(editor, tmp_path):
    client = TestClient(create_app(editor))
    other = _write_feed(tmp_path / "other.zip", "z9", 60.30, 25.10)
    second = client.post("/api/catalogue", json={"path": str(other), "name": "Metro"})
    first_id = client.get("/api/catalogue").json()["feeds"][0]["feed_id"]
    second_id = second.json()["feed_id"]

    # an unsaved edit on the first feed must reach the merged result
    assert (
        client.patch("/api/stops/s1", json={"stop_name": "Kamppi M"}).status_code == 200
    )

    merged = client.post(
        "/api/catalogue/merge", json={"feed_ids": [first_id, second_id]}
    )
    assert merged.status_code == 200
    entry = merged.json()
    assert entry["current"] is True and entry["active"] is True
    assert entry["source"] is None
    assert entry["dropped_files"] == []
    assert entry["name"].startswith("feed.zip + Metro")
    assert entry["tables"]["stops.txt"] == 3  # 2 + 1
    assert entry["tables"]["agency.txt"] == 2

    rows = client.get("/api/tables/stops.txt").json()["rows"]
    names = {row["stop_name"] for row in rows}
    assert "Kamppi M" in names  # the live edit, not the file on disk
    ids = {row["stop_id"] for row in rows}
    assert all(":" in stop_id for stop_id in ids)  # namespaced per source feed

    # the merged feed is editable and saveable like any other loaded feed
    assert (
        client.patch(
            f"/api/stops/{rows[0]['stop_id']}", json={"stop_name": "M"}
        ).status_code
        == 200
    )
    assert client.post("/api/save", json={}).status_code == 422  # no source path
    saved = client.post(
        "/api/save", json={"path": str(tmp_path / "merged.zip"), "check": False}
    )
    assert saved.status_code == 200 and (tmp_path / "merged.zip").exists()


def test_catalogue_merge_names_and_drops(editor, tmp_path):
    import pandas as pd

    editor.tables["feed_info.txt"] = pd.DataFrame(
        {"feed_publisher_name": ["HSL"], "feed_lang": ["fi"]}
    )
    client = TestClient(create_app(editor))
    other = _write_feed(tmp_path / "other.zip", "z9", 60.30, 25.10)
    second = client.post("/api/catalogue", json={"path": str(other)}).json()
    first_id = client.get("/api/catalogue").json()["feeds"][0]["feed_id"]

    merged = client.post(
        "/api/catalogue/merge",
        json={"feed_ids": [first_id, second["feed_id"]], "name": "Combined"},
    ).json()
    # feed_info describes one source feed, so the merge drops and reports it
    assert merged["dropped_files"] == ["feed_info.txt"]
    assert "feed_info.txt" not in merged["tables"]

    entry = client.get("/api/catalogue").json()["feeds"][-1]
    assert entry["name"] == "Combined" and entry["current"] is True
    assert "dropped_files" not in entry  # response-only, never persisted


def test_catalogue_merge_into_chosen_folder(editor, tmp_path):
    client = TestClient(create_app(editor))
    other = _write_feed(tmp_path / "other.zip", "z9", 60.30, 25.10)
    second = client.post("/api/catalogue", json={"path": str(other)}).json()
    first_id = client.get("/api/catalogue").json()["feeds"][0]["feed_id"]
    target = tmp_path / "out" / "nested"  # created on demand

    merged = client.post(
        "/api/catalogue/merge",
        json={
            "feed_ids": [first_id, second["feed_id"]],
            "name": "Helsinki region",
            "directory": str(target),
        },
    ).json()
    written = target / "Helsinki-region.zip"  # name sanitised into a filename
    assert merged["saved"] == str(written) and written.exists()
    # the entry keeps the path, so a later save goes back to the same file
    assert merged["source"] == str(written)
    assert client.post("/api/save", json={}).status_code == 200
    assert FeedEditor(written).tables["stops.txt"].shape[0] == 3
    before = written.read_bytes()

    assert (
        client.post(
            "/api/catalogue/merge",
            json={"feed_ids": [first_id, second["feed_id"]], "directory": ""},
        ).status_code
        == 422
    )
    # merging again under the same name must not overwrite the first file
    again = client.post(
        "/api/catalogue/merge",
        json={
            "feed_ids": [first_id, second["feed_id"]],
            "name": "Helsinki region",
            "directory": str(target),
        },
    )
    assert again.status_code == 409
    assert written.read_bytes() == before


def test_catalogue_merge_errors(editor, tmp_path):
    client = TestClient(create_app(editor))
    first_id = client.get("/api/catalogue").json()["feeds"][0]["feed_id"]
    other = _write_feed(tmp_path / "other.zip", "z9", 60.30, 25.10)
    second_id = client.post("/api/catalogue", json={"path": str(other)}).json()[
        "feed_id"
    ]
    for body in (
        {},
        {"feed_ids": first_id},
        {"feed_ids": [first_id]},
        {"feed_ids": [first_id, 5]},
        {"feed_ids": [first_id, first_id]},  # a feed cannot merge with itself
        {"feed_ids": [first_id, "nope"]},
    ):
        assert client.post("/api/catalogue/merge", json=body).status_code == 422

    assert second_id  # both feeds are in the catalogue

    # a GTFS-Flex feed cannot be namespaced, so the merge is refused
    flex = FeedEditor(other)
    flex.tables["stop_times.txt"]["location_id"] = "loc"
    flex_client = TestClient(create_app(flex))
    flex_first = flex_client.get("/api/catalogue").json()["feeds"][0]["feed_id"]
    flex_second = flex_client.post("/api/catalogue", json={"path": str(other)}).json()[
        "feed_id"
    ]
    refused = flex_client.post(
        "/api/catalogue/merge", json={"feed_ids": [flex_first, flex_second]}
    )
    assert refused.status_code == 422
    assert "location_id" in refused.json()["detail"]


def test_catalogue_groups_round_trip(editor, tmp_path):
    client = TestClient(create_app(editor))
    other = _write_feed(tmp_path / "other.zip", "z9", 60.30, 25.10)
    second = client.post("/api/catalogue", json={"path": str(other)}).json()
    first_id = client.get("/api/catalogue").json()["feeds"][0]["feed_id"]

    created = client.post("/api/catalogue/groups", json={"name": "Cropped feeds"})
    assert created.status_code == 200
    assert created.json()["groups"] == ["Cropped feeds"]
    # a group with a slash in its name is addressable: names travel in
    # the body (or a query parameter), never in the path
    client.post("/api/catalogue/groups", json={"name": "a/b"})

    filed = client.patch(f"/api/catalogue/{first_id}", json={"group": "Cropped feeds"})
    assert filed.json()["group"] == "Cropped feeds"

    renamed = client.patch(
        "/api/catalogue/groups",
        json={"name": "Cropped feeds", "new_name": "Helsinki area"},
    )
    assert renamed.json()["groups"] == ["Helsinki area", "a/b"]
    feeds = {f["feed_id"]: f for f in client.get("/api/catalogue").json()["feeds"]}
    assert feeds[first_id]["group"] == "Helsinki area"  # membership follows
    assert feeds[second["feed_id"]]["group"] is None

    # the slash name survives a rename and a delete through the query
    # parameter, which is why names never sit in the path
    client.patch(f"/api/catalogue/{second['feed_id']}", json={"group": "a/b"})
    assert client.patch(
        "/api/catalogue/groups", json={"name": "a/b", "new_name": "c/d"}
    ).json()["groups"] == ["Helsinki area", "c/d"]
    # renaming onto an existing name is refused
    assert (
        client.patch(
            "/api/catalogue/groups", json={"name": "c/d", "new_name": "Helsinki area"}
        ).status_code
        == 422
    )
    assert (
        client.delete("/api/catalogue/groups", params={"name": "c/d"}).status_code
        == 200
    )

    removed = client.delete("/api/catalogue/groups", params={"name": "Helsinki area"})
    assert removed.json()["groups"] == []
    body = client.get("/api/catalogue").json()
    assert body["groups"] == []
    # the feed outlives its group, ungrouped
    assert len(body["feeds"]) == 2
    assert all(feed["group"] is None for feed in body["feeds"])


def test_catalogue_group_errors(editor):
    client = TestClient(create_app(editor))
    feed_id = client.get("/api/catalogue").json()["feeds"][0]["feed_id"]
    client.post("/api/catalogue/groups", json={"name": "Group"})

    for body in (
        {},
        {"name": ""},
        {"name": "  "},
        {"name": 5},
        {"name": "x" * 61},
    ):
        assert client.post("/api/catalogue/groups", json=body).status_code == 422
    # a lone surrogate arrives as a JSON escape (it cannot be encoded as
    # UTF-8) and would break every later catalogue response if stored
    assert (
        client.post(
            "/api/catalogue/groups",
            content=r'{"name": "bad\ud800"}',
            headers={"content-type": "application/json"},
        ).status_code
        == 422
    )
    # duplicates are refused rather than silently merged
    assert (
        client.post("/api/catalogue/groups", json={"name": "Group"}).status_code == 422
    )
    assert (
        client.patch(
            "/api/catalogue/groups", json={"name": "nope", "new_name": "x"}
        ).status_code
        == 404
    )
    assert (
        client.patch(
            "/api/catalogue/groups", json={"name": "Group", "new_name": " "}
        ).status_code
        == 422
    )
    assert (
        client.delete("/api/catalogue/groups", params={"name": "nope"}).status_code
        == 404
    )
    # an unknown group on a feed is refused, so a typo cannot hide a feed
    assert (
        client.patch(f"/api/catalogue/{feed_id}", json={"group": "typo"}).status_code
        == 422
    )
    assert (
        client.patch(f"/api/catalogue/{feed_id}", json={"group": None}).status_code
        == 200
    )


def _write_feed_at(path, stops):
    """A feed with one two-stop trip per given stop id."""
    b = FeedBuilder()
    b.add_agency("a", "A", "https://a.example", "Europe/Helsinki")
    b.add_route("r", 3, "1", agency_id="a")
    b.add_service("wk", "weekdays", "20260101", "20261231")
    for stop_id, lat, lon in stops:
        b.add_stop(stop_id, stop_id, lat, lon)
        b.add_trip(
            "r",
            "wk",
            f"t-{stop_id}",
            [(stop_id, "08:00:00", "08:00:00"), (stop_id, "08:05:00", "08:05:00")],
        )
    b.save(path, check=False)
    return path


INSIDE = (60.12, 24.93)
OUTSIDE = (61.5, 27.0)
CITY_BOX = [24.9, 60.1, 25.0, 60.2]
CITY_POLYGON = {
    "type": "Polygon",
    # a triangle covering the western half of CITY_BOX only
    "coordinates": [[[24.90, 60.10], [24.95, 60.10], [24.90, 60.20], [24.90, 60.10]]],
}


def test_crop_creates_copies_in_a_group(tmp_path):
    source = _write_feed_at(
        tmp_path / "city.zip", [("in1", *INSIDE), ("out1", *OUTSIDE)]
    )
    client = TestClient(create_app(FeedEditor(source)))
    other = _write_feed_at(tmp_path / "far.zip", [("z1", *OUTSIDE)])
    client.post("/api/catalogue", json={"path": str(other), "name": "Far"})

    body = client.post("/api/catalogue/crop", json={"shape": CITY_BOX}).json()
    # the feed with nothing inside is reported, not created
    assert body["empty"] == ["Far"]
    assert body["skipped"] == []
    assert len(body["feeds"]) == 1
    cropped = body["feeds"][0]
    assert cropped["name"] == "city.zip (cropped)"
    assert cropped["group"] == "Cropped feeds"
    assert cropped["source"] is None  # a copy, saved wherever the user says
    assert cropped["tables"]["stops.txt"] == 1  # only the inside stop
    assert body["groups"] == ["Cropped feeds"]

    # the sources are untouched
    feeds = client.get("/api/catalogue").json()["feeds"]
    assert feeds[0]["tables"]["stops.txt"] == 2
    assert len(feeds) == 3


def test_crop_uses_live_edits_and_polygon_shape(tmp_path):
    # in1 is inside the triangle; in2 is in its bounding box but outside
    # the triangle itself
    source = _write_feed_at(
        tmp_path / "city.zip", [("in1", *INSIDE), ("in2", 60.17, 24.98)]
    )
    client = TestClient(create_app(FeedEditor(source)))
    assert (
        client.patch("/api/stops/in1", json={"stop_name": "Renamed"}).status_code == 200
    )

    # the triangle covers in1 (24.93) but not in2 (24.98), unlike the box
    body = client.post(
        "/api/catalogue/crop", json={"shape": CITY_POLYGON, "group": "West"}
    ).json()
    assert body["feeds"][0]["tables"]["stops.txt"] == 1
    assert body["feeds"][0]["group"] == "West"
    client.put("/api/catalogue/current", json={"feed_id": body["feeds"][0]["feed_id"]})
    rows = client.get("/api/tables/stops.txt").json()["rows"]
    assert [row["stop_name"] for row in rows] == ["Renamed"]  # unsaved edit kept

    box = client.post("/api/catalogue/crop", json={"shape": CITY_BOX}).json()
    # the same box keeps both stops: the polygon was not its bounding box
    assert box["feeds"][0]["tables"]["stops.txt"] >= 2


def test_crop_selected_feeds_and_full_trips_only(tmp_path):
    source = _write_feed_at(
        tmp_path / "city.zip", [("in1", *INSIDE), ("out1", *OUTSIDE)]
    )
    client = TestClient(create_app(FeedEditor(source)))

    # one trip crossing the boundary: kept whole by default, dropped when
    # only wholly-inside trips count
    crossing = FeedBuilder()
    crossing.add_agency("a", "A", "https://a.example", "Europe/Helsinki")
    crossing.add_stop("here", "here", *INSIDE)
    crossing.add_stop("away", "away", *OUTSIDE)
    crossing.add_route("r", 3, "1", agency_id="a")
    crossing.add_service("wk", "weekdays", "20260101", "20261231")
    crossing.add_trip(
        "r",
        "wk",
        "t-cross",
        [("here", "08:00:00", "08:00:00"), ("away", "09:00:00", "09:00:00")],
    )
    path = tmp_path / "crossing.zip"
    crossing.save(path, check=False)
    second = client.post("/api/catalogue", json={"path": str(path)}).json()

    only = client.post(
        "/api/catalogue/crop",
        json={"shape": CITY_BOX, "feed_ids": [second["feed_id"]]},
    ).json()
    # only the named feed was cropped, and the crossing trip survived whole
    assert [feed["name"] for feed in only["feeds"]] == ["crossing.zip (cropped)"]
    assert only["feeds"][0]["tables"]["stops.txt"] == 2  # the outside stop too

    strict = client.post(
        "/api/catalogue/crop",
        json={
            "shape": CITY_BOX,
            "feed_ids": [second["feed_id"]],
            "full_trips_only": True,
        },
    ).json()
    # the only trip leaves the area, so nothing is left to crop
    assert strict["feeds"] == []
    assert strict["empty"] == ["crossing.zip"]


def test_crop_accepts_a_ring_with_a_repeated_vertex(tmp_path):
    source = _write_feed_at(tmp_path / "city.zip", [("in1", *INSIDE)])
    client = TestClient(create_app(FeedEditor(source)))
    # an extra click on the same spot must not make the area degenerate
    doubled = {
        "type": "Polygon",
        "coordinates": [
            [
                [24.90, 60.10],
                [24.90, 60.10],
                [25.00, 60.10],
                [25.00, 60.20],
                [24.90, 60.10],
            ]
        ],
    }
    body = client.post("/api/catalogue/crop", json={"shape": doubled})
    assert body.status_code == 200
    assert len(body.json()["feeds"]) == 1


def test_crop_rejects_bad_requests(tmp_path):
    source = _write_feed_at(tmp_path / "city.zip", [("in1", *INSIDE)])
    client = TestClient(create_app(FeedEditor(source)))
    for body in (
        {},
        {"shape": None},
        {"shape": "everywhere"},
        {"shape": [1, 2, 3]},
        {"shape": [1, 2, "east", 4]},
        {"shape": [25.0, 60.2, 24.9, 60.1]},  # reversed
        {"shape": {"type": "Point", "coordinates": [0, 0]}},
        {"shape": CITY_BOX, "feed_ids": ["nope"]},
        {"shape": CITY_BOX, "feed_ids": "feed-1"},
        {"shape": CITY_BOX, "feed_ids": ["feed-1", "feed-1"]},
        {"shape": CITY_BOX, "full_trips_only": "yes"},
        {"shape": [10**400, 60.1, 25.0, 60.2]},  # beyond the float range
        {"shape": [True, 60.1, 25.0, 60.2]},  # a bool is not a coordinate
        {"shape": [24.9, 60.1, 200.0, 60.2]},  # outside WGS84
        {"shape": CITY_BOX, "group": "x" * 61},
        # structurally fine but bounding no area
        {
            "shape": {
                "type": "Polygon",
                "coordinates": [[[24.9, 60.1], [25.0, 60.1], [25.1, 60.1]]],
            }
        },
        {"shape": {"type": "MultiPolygon", "coordinates": [[]]}},
        {"shape": CITY_BOX, "group": "  "},
        # a polygon that cannot bound an area
        {"shape": {"type": "Polygon", "coordinates": [[[0, 0], [1, 1]]]}},
    ):
        assert client.post("/api/catalogue/crop", json=body).status_code == 422, body


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


def test_scratch_builder_entry_carries_no_feed_content():
    # A launch without a feed opens on an empty builder; the GUI reads this
    # entry's empty source and tables to know it has nothing to show yet.
    client = TestClient(create_app(FeedBuilder()))
    entry = client.get("/api/catalogue").json()["feeds"][0]
    assert entry["source"] is None
    assert entry["tables"] == {}


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
        self.directories = getattr(self, "directories", [])
        self.directories.append(directory)
        if self._download_path is None:
            raise RuntimeError("download unavailable")
        if directory is not None:
            # mirror the real client: the zip lands in the given directory
            import shutil
            from pathlib import Path

            target = Path(directory) / Path(self._download_path).name
            shutil.copy(self._download_path, target)
            return target
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


def test_search_by_place_geocodes_and_reports_it(editor, monkeypatch):
    import transitio_editor._app as app_module

    monkeypatch.setattr(
        app_module, "_place_bbox", lambda query: (24.8, 60.0, 25.3, 60.4)
    )
    stub = _StubCatalog([_catalog_feed()], token="tok")
    client = TestClient(create_app(editor, catalog_factory=lambda: stub))
    body = client.get("/api/search", params={"q": " Helsinki "}).json()
    # the geocoded box drives the feed search...
    assert stub.calls[0]["aoi"] == (24.8, 60.0, 25.3, 60.4)
    # ...and comes back so the map can fly there
    assert body["place"] == {"query": "Helsinki", "bbox": [24.8, 60.0, 25.3, 60.4]}
    assert [feed["id"] for feed in body["feeds"]] == ["mdb-1"]

    # a typed place decides the area even when a bbox is also sent —
    # including a malformed one, which is ignored rather than validated
    client.get("/api/search", params={"q": "Helsinki", "bbox": "0,0,1,1"})
    assert stub.calls[1]["aoi"] == (24.8, 60.0, 25.3, 60.4)
    ok = client.get("/api/search", params={"q": "Helsinki", "bbox": "garbage"})
    assert ok.status_code == 200

    # a blank query is no place search at all
    body = client.get("/api/search", params={"q": "  "}).json()
    assert "place" not in body
    assert stub.calls[-1]["aoi"] is None


def test_search_place_not_found_is_422(editor, monkeypatch):
    import transitio_editor._app as app_module

    def refuse(query):
        raise ValueError("Nominatim found nothing")

    monkeypatch.setattr(app_module, "_place_bbox", refuse)
    stub = _StubCatalog([], token="tok")
    client = TestClient(create_app(editor, catalog_factory=lambda: stub))
    response = client.get("/api/search", params={"q": "Atlantis"})
    assert response.status_code == 422
    assert "Atlantis" in response.json()["detail"]
    assert stub.calls == []  # never reached the catalogue


def test_place_bbox_pads_tiny_places(monkeypatch):
    import transitio_editor._app as app_module

    # a village geocoded to a point still yields a searchable area
    monkeypatch.setattr(
        app_module, "_geocode_bounds", lambda query: (24.9, 60.1, 24.9, 60.1)
    )
    minx, miny, maxx, maxy = app_module._place_bbox("somewhere")
    assert maxx - minx == pytest.approx(0.1)
    assert maxy - miny == pytest.approx(0.05)

    # a city-sized box is left alone
    monkeypatch.setattr(
        app_module, "_geocode_bounds", lambda query: (24.5, 59.9, 25.5, 60.4)
    )
    assert app_module._place_bbox("city") == (24.5, 59.9, 25.5, 60.4)

    # at a WGS84 corner the box shifts inward instead of shrinking
    monkeypatch.setattr(
        app_module, "_geocode_bounds", lambda query: (179.99, 89.99, 180.0, 90.0)
    )
    minx, miny, maxx, maxy = app_module._place_bbox("pole")
    assert maxx <= 180 and maxy <= 90
    assert maxx - minx == pytest.approx(0.1)
    assert maxy - miny == pytest.approx(0.05)


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
    # the origin records the Mobility DB id, so the search list can mark
    # already-downloaded feeds; locally loaded feeds carry no origin
    assert entry["origin"] == "mdb-1"
    assert entry["modes"] == [3]  # the downloaded fixture is a bus feed
    local = client.get("/api/catalogue").json()["feeds"][0]
    assert local["origin"] is None
    assert local["modes"] == [0]  # the editor fixture's route is a tram
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


def _two_area_feed(path):
    # a valid feed with a Helsinki trip and a far-away (0, 0) trip.
    b = FeedBuilder()
    b.add_agency("a", "A", "https://a.example", "Europe/Helsinki")
    b.add_route("r", 3, "1", agency_id="a")
    b.add_service("wk", "weekdays", "20260101", "20261231")
    b.add_stop("h1", "Kamppi", 60.169, 24.931)
    b.add_stop("h2", "Steissi", 60.171, 24.941)
    b.add_stop("f1", "Far1", 0.0, 0.0)
    b.add_stop("f2", "Far2", 0.001, 0.001)
    b.add_frequency_trip(
        "r",
        "wk",
        "th",
        [("h1", 0), ("h2", 300)],
        start="06:00:00",
        end="09:00:00",
        headway=600,
    )
    b.add_frequency_trip(
        "r",
        "wk",
        "tf",
        [("f1", 0), ("f2", 300)],
        start="06:00:00",
        end="09:00:00",
        headway=600,
    )
    b.save(path, reference_date="20260601")
    return str(path)


_HELSINKI_AOI = [24.90, 60.16, 24.96, 60.18]


def test_download_crops_to_aoi(editor, tmp_path):
    zip_path = _two_area_feed(tmp_path / "two.zip")
    stub = _StubCatalog([_catalog_feed()], token="tok", download_path=zip_path)
    client = TestClient(create_app(editor, catalog_factory=lambda: stub))
    client.get("/api/search")  # populate the download cache
    entry = client.post(
        "/api/catalogue/download", json={"feed_id": "mdb-1", "aoi": _HELSINKI_AOI}
    ).json()
    # only the Helsinki trip survives; the far stops cascade away
    assert entry["tables"]["stops.txt"] == 2
    assert entry["tables"]["trips.txt"] == 1
    assert ".aoi-" in entry["source"] and entry["source"].endswith(".zip")
    # the cropped feed is referentially consistent across the main foreign keys
    t = FeedEditor(entry["source"]).tables
    assert set(t["stop_times.txt"]["stop_id"]) <= {"h1", "h2"}
    assert set(t["stop_times.txt"]["trip_id"]) <= set(t["trips.txt"]["trip_id"])
    assert set(t["trips.txt"]["route_id"]) <= set(t["routes.txt"]["route_id"])
    assert set(t["trips.txt"]["service_id"]) <= set(t["calendar.txt"]["service_id"])
    assert set(t["frequencies.txt"]["trip_id"]) <= set(t["trips.txt"]["trip_id"])


def test_download_without_aoi_is_full(editor, tmp_path):
    zip_path = _two_area_feed(tmp_path / "two.zip")
    stub = _StubCatalog([_catalog_feed()], token="tok", download_path=zip_path)
    client = TestClient(create_app(editor, catalog_factory=lambda: stub))
    client.get("/api/search")
    entry = client.post("/api/catalogue/download", json={"feed_id": "mdb-1"}).json()
    assert entry["tables"]["stops.txt"] == 4 and entry["tables"]["trips.txt"] == 2
    assert ".aoi-" not in entry["source"]


def test_download_crop_writes_provenance(editor, tmp_path):
    import json

    zip_path = _two_area_feed(tmp_path / "two.zip")
    stub = _StubCatalog([_catalog_feed()], token="tok", download_path=zip_path)
    client = TestClient(create_app(editor, catalog_factory=lambda: stub))
    client.get("/api/search")
    entry = client.post(
        "/api/catalogue/download", json={"feed_id": "mdb-1", "aoi": _HELSINKI_AOI}
    ).json()
    sidecar = entry["source"] + ".provenance.json"
    data = json.loads(open(sidecar).read())
    assert data["aoi_bbox"] == _HELSINKI_AOI
    assert data["row_counts"]["stops.txt"] == 2 and data["source_dataset"]


def test_download_into_chosen_directory(editor, tmp_path):
    zip_path = _write_feed(tmp_path / "dl.zip", "d1", 60.4, 25.2)
    stub = _StubCatalog([_catalog_feed()], token="tok", download_path=zip_path)
    client = TestClient(create_app(editor, catalog_factory=lambda: stub))
    client.get("/api/search")
    target = tmp_path / "work" / "nyc"  # created on demand
    entry = client.post(
        "/api/catalogue/download",
        json={"feed_id": "mdb-1", "directory": str(target)},
    ).json()
    assert stub.directories[-1] == target
    assert entry["source"].startswith(str(target))
    # a cropped download lands beside its zip in the same directory
    two_area = _two_area_feed(tmp_path / "two.zip")
    stub._download_path = two_area
    cropped = client.post(
        "/api/catalogue/download",
        json={"feed_id": "mdb-1", "directory": str(target), "aoi": _HELSINKI_AOI},
    ).json()
    assert cropped["source"].startswith(str(target)) and ".aoi-" in cropped["source"]
    # invalid directory values are rejected up front
    assert (
        client.post(
            "/api/catalogue/download", json={"feed_id": "mdb-1", "directory": 5}
        ).status_code
        == 422
    )
    assert (
        client.post(
            "/api/catalogue/download", json={"feed_id": "mdb-1", "directory": "  "}
        ).status_code
        == 422
    )


def test_download_rejects_bad_aoi(editor):
    stub = _StubCatalog([_catalog_feed()], token="tok")
    client = TestClient(create_app(editor, catalog_factory=lambda: stub))
    # bad bbox is rejected before any download (no search needed)
    got = client.post(
        "/api/catalogue/download",
        json={"feed_id": "mdb-1", "aoi": [400, 60, 25, 61]},
    )
    assert got.status_code == 422


def test_add_stop_out_of_range_coord_is_422(editor):
    # a JSON integer beyond float range must be a 422, not an uncaught 500.
    client = TestClient(create_app(editor))
    got = client.post(
        "/api/stops",
        json={"stop_id": "x", "stop_name": "X", "stop_lat": 10**400, "stop_lon": 24.9},
    )
    assert got.status_code == 422


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
    # the source shows before the (lazy) load; counts appear only when loaded
    assert with_pbf.json() == {"available": True, "source": "fake.osm.pbf"}


def test_network_summary_counts_when_loaded(editor):
    client = TestClient(create_app(editor, osm_pbf=_osm_pbf(), network_type="driving"))
    client.get("/api/network/features")  # load the network
    body = client.get("/api/network").json()
    assert body["available"] is True and body["source"].endswith(".pbf")
    assert body["ways"] > 0 and body["nodes"] > 0


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
    summary = client.get("/api/network").json()
    assert summary["available"] is True and summary["source"] == got.json()["path"]
    assert summary["ways"] > 0  # loaded by the download, so counts are known
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


def test_shapes_carry_route_type(editor, tmp_path):
    # the fixture's shape belongs to a route_type 0 (tram) route
    client = TestClient(create_app(editor))
    (feature,) = client.get("/api/shapes").json()["features"]
    assert feature["properties"]["route_type"] == 0

    # extended route types normalise to their base family (700 -> bus 3)
    b = FeedBuilder()
    b.add_agency("a", "A", "https://a.example", "Europe/Helsinki")
    b.add_stop("s1", "S1", 60.1, 24.9)
    b.add_stop("s2", "S2", 60.2, 24.95)
    b.add_route("r", 700, "1", agency_id="a")
    b.add_service("wk", "weekdays", "20260101", "20261231")
    b.add_shape("sh", [(60.1, 24.9), (60.2, 24.95)])
    b.add_frequency_trip(
        "r",
        "wk",
        "t",
        [("s1", 0), ("s2", 300)],
        start="06:00:00",
        end="09:00:00",
        headway=600,
        shape_id="sh",
    )
    extended = TestClient(create_app(b))
    (feature,) = extended.get("/api/shapes").json()["features"]
    assert feature["properties"]["route_type"] == 3


def test_fs_dirs_lists_subdirectories(editor, tmp_path):
    client = TestClient(create_app(editor))
    (tmp_path / "alpha").mkdir()
    (tmp_path / "beta").mkdir()
    (tmp_path / ".hidden").mkdir()
    (tmp_path / "file.txt").write_text("x")
    body = client.get("/api/fs/dirs", params={"path": str(tmp_path)}).json()
    assert body["path"] == str(tmp_path)
    assert body["dirs"] == ["alpha", "beta"]  # sorted; no dotdirs, no files
    assert body["parent"] == str(tmp_path.parent)
    # navigating into a child works; bad paths are 404, not 500
    child = client.get("/api/fs/dirs", params={"path": str(tmp_path / "alpha")}).json()
    assert child["parent"] == str(tmp_path)
    assert (
        client.get("/api/fs/dirs", params={"path": str(tmp_path / "nope")}).status_code
        == 404
    )
    # a path pointing at a file browses the folder that holds it
    at_file = client.get("/api/fs/dirs", params={"path": str(tmp_path / "file.txt")})
    assert at_file.status_code == 200 and at_file.json()["path"] == str(tmp_path)
    # no path: the browser starts at the home directory
    from pathlib import Path

    assert client.get("/api/fs/dirs").json()["path"] == str(Path.home())


def test_fs_dirs_lists_feed_archives(editor, tmp_path):
    client = TestClient(create_app(editor))
    root = tmp_path / "browse"  # the fixture's own feed.zip lives in tmp_path
    (root / "sub").mkdir(parents=True)
    _write_feed(root / "b.zip", "z1", 60.1, 24.9)
    _write_feed(root / "a.zip", "z2", 60.2, 24.8)
    (root / "notes.txt").write_text("x")
    (root / ".hidden.zip").write_bytes(b"x")
    if hasattr(os, "mkfifo"):  # POSIX only
        os.mkfifo(root / "pipe.zip")  # not a feed, and opening it would hang
    body = client.get("/api/fs/dirs", params={"path": str(root)}).json()
    # feeds are the pickable *.zip files; other files and dotfiles are not
    assert body["feeds"] == ["a.zip", "b.zip"]
    assert body["dirs"] == ["sub"]
    # browsing to one of them lands in its folder, not a 404
    assert client.get("/api/fs/dirs", params={"path": str(root / "a.zip")}).json()[
        "path"
    ] == str(root)


def test_fs_dirs_skips_names_that_are_not_utf8(editor, tmp_path):
    client = TestClient(create_app(editor))
    root = tmp_path / "browse"
    root.mkdir()
    (root / "fine").mkdir()
    # a name that decodes only through surrogateescape would break the JSON
    # response; the listing skips it. Only filesystems that accept such a
    # name (Linux, not macOS or Windows) can exercise this.
    try:
        # Windows decodes filesystem bytes strictly, so even naming the
        # entry raises there; POSIX filesystems may still refuse it.
        os.mkdir(os.path.join(root, os.fsdecode(b"bad\xff")))
    except (OSError, ValueError):
        pytest.skip("this platform has no non-UTF-8 filenames")
    body = client.get("/api/fs/dirs", params={"path": str(root)})
    assert body.status_code == 200
    assert body.json()["dirs"] == ["fine"]


def test_table_search_filters_rows(editor):
    client = TestClient(create_app(editor))
    # substring across any column, case-insensitive
    body = client.get("/api/tables/stops.txt", params={"q": "kamppi"}).json()
    assert body["total"] == 1
    assert body["rows"][0]["stop_id"] == "s1"
    assert body["columns"]  # column list survives filtering
    # no match -> empty window, zero total
    empty = client.get("/api/tables/stops.txt", params={"q": "zzz"}).json()
    assert empty["total"] == 0 and empty["rows"] == []
    # blank q is a no-op
    full = client.get("/api/tables/stops.txt", params={"q": "  "}).json()
    assert full["total"] == 2


def test_reserved_route_types_normalise_to_unknown():
    from transitio_editor._registry import base_route_type

    # defined base codes pass through; reserved 8-10 and junk yield None
    assert [base_route_type(code) for code in (0, 7, 11, 12)] == [0, 7, 11, 12]
    assert base_route_type(8) is None
    assert base_route_type(9) is None
    assert base_route_type(10) is None
    assert base_route_type("x") is None


def test_bad_paths_are_client_errors(editor):
    # a NUL byte is invalid on every platform (an unknown ~user is not: on
    # Windows expanduser resolves it without raising), so it probes the
    # malformed-path handling portably: a 4xx, never an unhandled 500.
    nul_path = "bad" + chr(0) + "dir"
    client = TestClient(create_app(editor))
    assert client.get("/api/fs/dirs", params={"path": nul_path}).status_code == 404
    stub = _StubCatalog([_catalog_feed()], token="tok")
    with_dir = TestClient(create_app(editor, catalog_factory=lambda: stub))
    assert (
        with_dir.post(
            "/api/catalogue/download",
            json={"feed_id": "mdb-1", "directory": nul_path},
        ).status_code
        == 422
    )


def test_session_save_restore_round_trip(tmp_path):
    source = _write_feed_at(tmp_path / "city.zip", [("in1", *INSIDE)])
    client = TestClient(create_app(FeedEditor(source)))
    other = _write_feed_at(tmp_path / "other.zip", [("z1", *OUTSIDE)])
    second = client.post(
        "/api/catalogue", json={"path": str(other), "name": "Other"}
    ).json()
    # a sourceless feed (merged in memory) must be embedded by the save
    first_id = client.get("/api/catalogue").json()["feeds"][0]["feed_id"]
    merged = client.post(
        "/api/catalogue/merge",
        json={"feed_ids": [first_id, second["feed_id"]], "name": "Merged"},
    ).json()
    client.post("/api/catalogue/groups", json={"name": "Mine"})
    client.patch(f"/api/catalogue/{merged['feed_id']}", json={"group": "Mine"})
    client.patch(f"/api/catalogue/{second['feed_id']}", json={"active": False})
    client.put("/api/catalogue/current", json={"feed_id": second["feed_id"]})

    session = tmp_path / "work" / "helsinki.json"
    view = {"basemap": "dark", "camera": {"center": [24.9, 60.2], "zoom": 9}}
    saved = client.post("/api/session/save", json={"path": str(session), "view": view})
    assert saved.status_code == 200
    body = saved.json()
    assert body["embedded"] == ["Merged"]
    assert set(body["referenced"]) == {"city.zip", "Other"}
    assert session.exists()
    import json as json_module

    on_disk = json_module.loads(session.read_text())
    assert on_disk["transitio_editor_session"] == 1
    assert on_disk["view"] == view
    data_dir = tmp_path / "work" / "helsinki.data"
    assert len(list(data_dir.glob("*.zip"))) == 1  # the embedded feed only

    # a fresh app restores the lot
    restore_client = TestClient(create_app())
    restored = restore_client.post("/api/session/restore", json={"path": str(session)})
    assert restored.status_code == 200
    result = restored.json()
    assert result["view"] == view
    assert result["skipped"] == [] and result["warnings"] == []
    feeds = result["feeds"]
    assert [feed["name"] for feed in feeds] == ["city.zip", "Other", "Merged"]
    before = {
        feed["name"]: feed for feed in client.get("/api/catalogue").json()["feeds"]
    }
    for feed in feeds:
        assert feed["color"] == before[feed["name"]]["color"]
        assert feed["active"] == before[feed["name"]]["active"]
        assert feed["group"] == before[feed["name"]]["group"]
        assert feed["origin"] == before[feed["name"]]["origin"]
        assert feed["tables"] == before[feed["name"]]["tables"]
        assert feed["current"] == (feed["name"] == "Other")
    # the embedded feed is sourceless again: its zip is session storage
    assert before["Merged"]["source"] is None
    assert next(f for f in feeds if f["name"] == "Merged")["source"] is None

    # editing the restored embedded feed and re-saving embeds the edits
    restore_client.put(
        "/api/catalogue/current",
        json={"feed_id": next(f for f in feeds if f["name"] == "Merged")["feed_id"]},
    )
    stop = restore_client.get("/api/tables/stops.txt").json()["rows"][0]["stop_id"]
    restore_client.patch(f"/api/stops/{stop}", json={"stop_name": "Edited"})
    second_save = restore_client.post(
        "/api/session/save", json={"path": str(session)}
    ).json()
    assert second_save["embedded"] == ["Merged"]
    assert second_save["unreferenced_data_files"] == 1  # the first zip, kept
    assert len(list(data_dir.glob("*.zip"))) == 2  # fresh zip, old one left

    third = TestClient(create_app())
    third.post("/api/session/restore", json={"path": str(session)})
    third.put(
        "/api/catalogue/current",
        json={
            "feed_id": next(
                f
                for f in third.get("/api/catalogue").json()["feeds"]
                if f["name"] == "Merged"
            )["feed_id"]
        },
    )
    rows = third.get("/api/tables/stops.txt").json()["rows"]
    assert "Edited" in {row["stop_name"] for row in rows}


def test_session_restore_guards_and_skips(tmp_path):
    source = _write_feed_at(tmp_path / "city.zip", [("in1", *INSIDE)])
    client = TestClient(create_app(FeedEditor(source)))
    session = tmp_path / "s.json"
    client.post("/api/session/save", json={"path": str(session)})

    # loaded feeds require replace (an empty user group alone does too)
    conflict = client.post("/api/session/restore", json={"path": str(session)})
    assert conflict.status_code == 409
    assert conflict.json()["detail"]["reason"] == "feeds"
    grouped = TestClient(create_app())
    grouped.post("/api/catalogue/groups", json={"name": "Empty"})
    assert (
        grouped.post("/api/session/restore", json={"path": str(session)}).status_code
        == 409
    )
    ok = client.post(
        "/api/session/restore", json={"path": str(session), "replace": True}
    )
    assert ok.status_code == 200

    # a missing referenced file is a skip, not a failure; the first
    # restored feed becomes current when the recorded one was skipped
    other = _write_feed_at(tmp_path / "gone.zip", [("z1", *OUTSIDE)])
    client.post("/api/catalogue", json={"path": str(other), "name": "Gone"})
    gone_id = next(
        f for f in client.get("/api/catalogue").json()["feeds"] if f["name"] == "Gone"
    )["feed_id"]
    client.put("/api/catalogue/current", json={"feed_id": gone_id})
    client.post("/api/session/save", json={"path": str(session)})
    os.unlink(other)
    result = client.post(
        "/api/session/restore", json={"path": str(session), "replace": True}
    ).json()
    assert [skip["name"] for skip in result["skipped"]] == ["Gone"]
    assert any("current" in warning for warning in result["warnings"])
    assert [feed["name"] for feed in result["feeds"]] == ["city.zip"]
    assert result["feeds"][0]["current"] is True

    # a modified source restores with the checksum warning
    _write_feed_at(tmp_path / "city.zip", [("in1", *INSIDE), ("in2", 60.18, 24.95)])
    warned = client.post(
        "/api/session/restore", json={"path": str(session), "replace": True}
    ).json()
    assert any("changed since" in warning for warning in warned["warnings"])


def test_session_save_and_restore_reject_bad_input(tmp_path):
    client = TestClient(create_app(FeedBuilder()))
    for body in ({}, {"path": 5}, {"path": "s.txt"}, {"path": " "}):
        assert client.post("/api/session/save", json=body).status_code == 422
        assert client.post("/api/session/restore", json=body).status_code == 422
    assert (
        client.post(
            "/api/session/save", json={"path": str(tmp_path / "s.json"), "view": 5}
        ).status_code
        == 422
    )
    missing = client.post(
        "/api/session/restore", json={"path": str(tmp_path / "absent.json")}
    )
    assert missing.status_code == 422
    bad = tmp_path / "bad.json"
    bad.write_text("not json")
    assert (
        client.post("/api/session/restore", json={"path": str(bad)}).status_code == 422
    )
    wrong = tmp_path / "wrong.json"
    wrong.write_text('{"transitio_editor_session": 99}')
    assert (
        client.post("/api/session/restore", json={"path": str(wrong)}).status_code
        == 422
    )
    # a foreign non-empty directory where the data dir would go is refused
    source = _write_feed_at(tmp_path / "seed.zip", [("s", *INSIDE)])
    with_embedded = TestClient(create_app(FeedEditor(source)))
    first = with_embedded.get("/api/catalogue").json()["feeds"][0]["feed_id"]
    other = _write_feed_at(tmp_path / "o.zip", [("z", *OUTSIDE)])
    second = with_embedded.post("/api/catalogue", json={"path": str(other)}).json()
    with_embedded.post(
        "/api/catalogue/merge", json={"feed_ids": [first, second["feed_id"]]}
    )
    foreign = tmp_path / "mine.data"
    foreign.mkdir()
    (foreign / "precious.txt").write_text("keep me")
    refused = with_embedded.post(
        "/api/session/save", json={"path": str(tmp_path / "mine.json")}
    )
    assert refused.status_code == 422
    assert (foreign / "precious.txt").read_text() == "keep me"


def test_session_round_trips_osm_source(tmp_path, monkeypatch):
    source = _write_feed_at(tmp_path / "city.zip", [("in1", *INSIDE)])
    extract = tmp_path / "area.osm.pbf"
    extract.write_bytes(b"pbf")
    client = TestClient(create_app(FeedEditor(source), osm_pbf=extract))
    session = tmp_path / "s.json"
    client.post("/api/session/save", json={"path": str(session)})

    fresh = TestClient(create_app())
    body = fresh.post("/api/session/restore", json={"path": str(session)}).json()
    assert body["warnings"] == []
    # the source is re-pointed without the network having been loaded
    network = fresh.get("/api/network").json()
    assert network["source"] == str(extract)
    assert "nodes" not in network  # counts appear only once loaded

    # a vanished extract is a warning and cleared state, not a failure
    os.unlink(extract)
    cleared = TestClient(create_app())
    result = cleared.post("/api/session/restore", json={"path": str(session)}).json()
    assert any("OSM extract not found" in warning for warning in result["warnings"])
    assert cleared.get("/api/network").json()["available"] is False


def test_fs_dirs_lists_session_files(editor, tmp_path):
    client = TestClient(create_app(editor))
    root = tmp_path / "browse"
    root.mkdir()
    (root / "helsinki.json").write_text("{}")
    (root / ".hidden.json").write_text("{}")
    (root / "feed.zip").write_bytes(b"x")
    body = client.get("/api/fs/dirs", params={"path": str(root)}).json()
    assert body["sessions"] == ["helsinki.json"]
    assert body["feeds"] == ["feed.zip"]


def test_session_round_trips_origin(tmp_path):
    import json as json_module

    source = _write_feed_at(tmp_path / "city.zip", [("in1", *INSIDE)])
    session = tmp_path / "s.json"
    session.write_text(
        json_module.dumps(
            {
                "transitio_editor_session": 1,
                "groups": [],
                "feeds": [
                    {
                        "name": "Downloaded",
                        "source": str(source),
                        "sha256": None,
                        "color": None,
                        "group": None,
                        "origin": "mdb-123",
                        "active": True,
                        "current": True,
                        "embedded": False,
                    }
                ],
                "view": {},
                "osm_source": None,
            }
        )
    )
    client = TestClient(create_app())
    restored = client.post("/api/session/restore", json={"path": str(session)})
    assert restored.json()["feeds"][0]["origin"] == "mdb-123"
    # and a re-save carries it forward
    client.post("/api/session/save", json={"path": str(tmp_path / "again.json")})
    saved = json_module.loads((tmp_path / "again.json").read_text())
    assert saved["feeds"][0]["origin"] == "mdb-123"


def test_session_restore_needs_both_consents(tmp_path):
    source = _write_feed_at(tmp_path / "city.zip", [("in1", *INSIDE)])
    session_source = TestClient(create_app(FeedEditor(source)))
    session = tmp_path / "s.json"
    session_source.post("/api/session/save", json={"path": str(session)})

    dirty = TestClient(
        create_app(FeedEditor(source), osm_pbf=_osm_pbf(), network_type="driving")
    )
    assert (
        dirty.post(
            "/api/network/nodes", json={"lon": 26.94, "lat": 60.52, "tags": {}}
        ).status_code
        == 200
    )
    # loaded feeds and unsaved network edits are two separate refusals:
    # confirming one must not silently authorise the other
    first = dirty.post("/api/session/restore", json={"path": str(session)})
    assert first.status_code == 409 and first.json()["detail"]["reason"] == "feeds"
    second = dirty.post(
        "/api/session/restore", json={"path": str(session), "replace": True}
    )
    assert (
        second.status_code == 409 and second.json()["detail"]["reason"] == "osm-edits"
    )
    third = dirty.post(
        "/api/session/restore",
        json={"path": str(session), "replace": True, "discard_edits": True},
    )
    assert third.status_code == 200
    # the session had no OSM source, so the loaded network is gone
    assert dirty.get("/api/network").json()["available"] is False


@pytest.mark.skipif(os.name == "nt", reason="read-only directories are POSIX")
def test_session_save_rejects_unwritable_destination(tmp_path):
    import stat

    source = _write_feed_at(tmp_path / "city.zip", [("in1", *INSIDE)])
    client = TestClient(create_app(FeedEditor(source)))
    sealed = tmp_path / "sealed"
    sealed.mkdir()
    sealed.chmod(stat.S_IRUSR | stat.S_IXUSR)
    try:
        refused = client.post(
            "/api/session/save", json={"path": str(sealed / "s.json")}
        )
        assert refused.status_code == 422
    finally:
        sealed.chmod(0o755)
    assert list(sealed.iterdir()) == []  # no leaked temp file


@pytest.mark.skipif(os.name == "nt", reason="read-only directories are POSIX")
def test_failed_session_save_keeps_the_previous_one(tmp_path):
    import json as json_module
    import stat

    source = _write_feed_at(tmp_path / "seed.zip", [("s", *INSIDE)])
    client = TestClient(create_app(FeedEditor(source)))
    first = client.get("/api/catalogue").json()["feeds"][0]["feed_id"]
    other = _write_feed_at(tmp_path / "o.zip", [("z", *OUTSIDE)])
    second = client.post("/api/catalogue", json={"path": str(other)}).json()
    client.post(
        "/api/catalogue/merge",
        json={"feed_ids": [first, second["feed_id"]], "name": "Merged"},
    )
    session = tmp_path / "s.json"
    assert (
        client.post("/api/session/save", json={"path": str(session)}).status_code == 200
    )
    before = session.read_text()
    zips = list((tmp_path / "s.data").glob("*.zip"))

    (tmp_path / "s.data").chmod(stat.S_IRUSR | stat.S_IXUSR)  # no writing
    try:
        failed = client.post("/api/session/save", json={"path": str(session)})
        assert failed.status_code == 422
    finally:
        (tmp_path / "s.data").chmod(0o755)
    # the previous session and its zips are untouched and still restore
    assert session.read_text() == before
    assert list((tmp_path / "s.data").glob("*.zip")) == zips
    fresh = TestClient(create_app())
    restored = fresh.post("/api/session/restore", json={"path": str(session)})
    assert restored.status_code == 200
    assert json_module.loads(session.read_text())["transitio_editor_session"] == 1
