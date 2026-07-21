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
    snap_filter = None
    if args.snap_filter:
        import json

        try:
            snap_filter = json.loads(args.snap_filter)
        except json.JSONDecodeError as error:
            parser.error(f"--snap-filter is not valid JSON: {error}")
        if not isinstance(snap_filter, dict):
            parser.error("--snap-filter must be a JSON object")
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
        allowed_hosts=allowed,
    )
    print(f"transitio editor on http://{args.host}:{args.port}")
    uvicorn.run(app, host=args.host, port=args.port, log_level="warning")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
