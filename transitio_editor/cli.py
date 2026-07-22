"""The ``transitio-editor`` command line."""

from __future__ import annotations

import argparse
import pathlib


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="transitio-editor",
        description="edit a GTFS feed in the local map GUI",
    )
    parser.add_argument("feed", type=pathlib.Path, help="GTFS feed zip")
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
        default=50000,
        help="refuse to serve an OSM network larger than this many ways "
        "(default: 50000; 0 disables)",
    )
    parser.add_argument("--host", default="127.0.0.1", help="bind address")
    parser.add_argument("--port", type=int, default=8300, help="port")
    parser.add_argument(
        "--allow-remote",
        action="store_true",
        help="allow binding beyond loopback, exposing the UNAUTHENTICATED "
        "editor (feed reads, edits and saves) to the network",
    )
    args = parser.parse_args(argv)

    import uvicorn
    from transitio.edit import FeedEditor

    from transitio_editor import create_app

    if not args.feed.exists():
        parser.error(f"feed not found: {args.feed}")
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
    editor = FeedEditor(args.feed)
    # Host-header pinning stays on in remote mode: only the address the
    # server was bound under is accepted, not arbitrary rebindable names.
    allowed = None
    if args.allow_remote:
        host = f"[{args.host}]" if ":" in args.host else args.host
        allowed = [host, f"{host}:{args.port}"]
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
    print(f"transitio editor on http://{args.host}:{args.port}")
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
