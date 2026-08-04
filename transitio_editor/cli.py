"""The ``transitio-editor`` command line."""

from __future__ import annotations

import argparse
import http.client
import ipaddress
import json
import pathlib
import secrets
import threading
import time
import webbrowser


def _reachable_host(host):
    """An address a browser can open, from the address the server binds.

    A wildcard bind (any spelling — ``0.0.0.0``, ``::``,
    ``0:0:0:0:0:0:0:0``) accepts every interface but is not itself a
    destination; loopback of the same family is.
    """
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return host or "127.0.0.1"  # a hostname, or an empty bind
    if not address.is_unspecified:
        return host
    return "127.0.0.1" if address.version == 4 else "::1"


def _is_wildcard(host):
    try:
        return host == "" or ipaddress.ip_address(host).is_unspecified
    except ValueError:
        return False


def browser_url(host, port):
    """The address to open, given the address the server binds to.

    A wildcard bind is not a usable URL; reach the server over loopback
    instead, and bracket IPv6 literals.
    """
    host = _reachable_host(host)
    if ":" in host:  # an IPv6 literal
        host = f"[{host}]"
    return f"http://{host}:{port}"


def _this_editor_answers(target, port, token):
    """Whether THIS editor instance answers on the address.

    A 200 alone would also accept another editor (or any catch-all
    server) already holding the port while this one is doomed to fail
    its bind; the per-process boot token rules that out.
    """
    connection = http.client.HTTPConnection(target, port, timeout=0.25)
    try:
        connection.request("GET", "/api/boot-token")
        response = connection.getresponse()
        if response.status != 200:
            return False
        # a bounded read: a foreign service may stream forever, and its
        # body may be any JSON at all
        payload = json.loads(response.read(4096))
        return isinstance(payload, dict) and payload.get("token") == token
    except (OSError, ValueError, http.client.HTTPException):
        return False
    finally:
        connection.close()


def open_when_serving(url, host, port, token, timeout=10.0):
    """Open ``url`` in the default browser once this editor answers.

    Opening it before uvicorn is listening would land on a connection
    error, so a background thread polls the editor's API first. Returns
    the thread so callers can join it; failures are silent — a machine
    without a browser must not take the server down with it.
    """
    target = _reachable_host(host)

    def wait_and_open():
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if _this_editor_answers(target, port, token):
                break
            time.sleep(0.1)
        else:
            return  # never came up: leave the printed URL as the way in
        try:
            webbrowser.open(url)
        except Exception:  # noqa: B902
            pass  # no browser here; the URL is on stdout

    thread = threading.Thread(target=wait_and_open, daemon=True)
    thread.start()
    return thread


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="transitio-editor",
        description="edit a GTFS feed in the local map GUI",
    )
    parser.add_argument(
        "feed",
        nargs="?",
        type=pathlib.Path,
        help="GTFS feed zip; omit to start empty and build a feed from "
        "scratch or load feeds from the GUI",
    )
    parser.add_argument(
        "--osm-pbf",
        type=pathlib.Path,
        help="OSM extract enabling snapped shape drawing",
    )
    parser.add_argument(
        "--network-type",
        default="driving",
        help="pyrosm network type for snapping (default: driving)",
    )
    parser.add_argument(
        "--snap-filter",
        metavar="JSON",
        help='default pyrosm tag filter for snapping, e.g. \'{"railway": '
        '["tram"]}\' to snap to tram rails (overrides --network-type)',
    )
    parser.add_argument(
        "--network-filter",
        metavar="JSON",
        help="pyrosm tag filter selecting the editable OSM network shown in "
        "the Network tab (default: all highways plus tram/rail/light_rail/"
        "subway)",
    )
    parser.add_argument(
        "--max-network-ways",
        type=int,
        default=200000,
        help="refuse to serve an OSM network larger than this many ways "
        "(default: 200000; 0 disables)",
    )
    parser.add_argument("--host", default="127.0.0.1", help="bind address")
    parser.add_argument("--port", type=int, default=8300, help="port")
    parser.add_argument(
        "--allow-remote",
        action="store_true",
        help="allow binding beyond loopback, exposing the UNAUTHENTICATED "
        "editor (feed reads, edits and saves) to the network",
    )
    parser.add_argument(
        "--no-browser",
        action="store_true",
        help="do not open the GUI in the default browser on startup",
    )
    args = parser.parse_args(argv)

    import uvicorn
    from transitio.edit import FeedBuilder, FeedEditor

    from transitio_editor import create_app

    if args.feed is not None and not args.feed.exists():
        parser.error(f"feed not found: {args.feed}")
    if not 1 <= args.port <= 65535:
        # port 0 would bind an ephemeral port the printed URL cannot name
        parser.error(f"port must be between 1 and 65535, not {args.port}")
    if args.host not in ("127.0.0.1", "localhost", "::1") and not args.allow_remote:
        parser.error(
            "the editor has no authentication; refusing a non-loopback "
            "host without --allow-remote"
        )

    def _json_filter(value, flag):
        import json

        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as error:
            parser.error(f"{flag} is not valid JSON: {error}")
        if not isinstance(parsed, dict):
            parser.error(f"{flag} must be a JSON object")
        return parsed

    snap_filter = (
        _json_filter(args.snap_filter, "--snap-filter") if args.snap_filter else None
    )
    network_filter = (
        _json_filter(args.network_filter, "--network-filter")
        if args.network_filter
        else None
    )
    # Without a feed the editor opens on an empty builder: build a feed from
    # scratch on the Edit tab, or load/download feeds via Catalogue/Search.
    editor = FeedEditor(args.feed) if args.feed is not None else FeedBuilder()
    # Host-header pinning stays on in remote mode: only the address the
    # server was bound under is accepted, not arbitrary rebindable names.
    allowed = None
    if args.allow_remote:
        host = f"[{args.host}]" if ":" in args.host else args.host
        allowed = [host, f"{host}:{args.port}"]
        if _is_wildcard(args.host):
            # a wildcard bind serves loopback too, and loopback is what
            # the browser is pointed at
            allowed += [
                name
                for loopback in ("localhost", "127.0.0.1", "[::1]")
                for name in (loopback, f"{loopback}:{args.port}")
            ]
    elif args.host == "::1":
        allowed = ["[::1]", f"[::1]:{args.port}", "localhost", "127.0.0.1"]
    app = create_app(
        editor,
        osm_pbf=args.osm_pbf,
        network_type=args.network_type,
        snap_custom_filter=snap_filter,
        network_filter=network_filter,
        max_network_ways=args.max_network_ways,
        allowed_hosts=allowed,
    )
    # The token names this process, so the poller cannot mistake another
    # editor (or any other service) on the port for this one.
    boot_token = secrets.token_hex(16)

    @app.get("/api/boot-token")
    def _boot_token():
        return {"token": boot_token}

    url = browser_url(args.host, args.port)
    print(f"transitio editor on {url}", flush=True)
    if not args.no_browser:
        open_when_serving(url, args.host, args.port, boot_token)
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
