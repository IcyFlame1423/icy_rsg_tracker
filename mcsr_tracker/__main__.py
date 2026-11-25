"""Command line: python -m mcsr_tracker <command>"""

import argparse
import sys

from .config import load_config
from .importer import import_records
from .watch import watch


def main(argv=None):
    parser = argparse.ArgumentParser(prog="mcsr_tracker", description="MCSR RSG run tracker")
    parser.add_argument("--config", help="path to config.toml")
    sub = parser.add_subparsers(dest="command")

    imp = sub.add_parser("import", help="add new SpeedRunIGT records to runs.csv and update stats")
    imp.add_argument("--rebuild", action="store_true",
                     help="rebuild runs.csv from the records folder only (old file kept as runs.csv.bak)")

    a = sub.add_parser("app", help="open the dashboard and keep the CSVs updated (default)")
    a.add_argument("--port", type=int, default=8765, help="port to serve on (default 8765)")
    a.add_argument("--no-browser", action="store_true", help="don't open a browser window")
    a.add_argument("--no-tracker", action="store_true", help="only show data; don't import runs")

    w = sub.add_parser("watch", help="keep the CSVs updated while you play (console only)")
    w.add_argument("--interval", type=float, default=None,
                   help="seconds between checks for new records (default: from config, 3)")

    args = parser.parse_args(argv)
    cfg = load_config(args.config) if args.config else load_config()

    if args.command in (None, "app"):
        # The app starts even if the records folder is wrong: it can be fixed in Settings.
        from .app.server import run_app
        run_app(cfg, port=getattr(args, "port", 8765),
                open_browser=not getattr(args, "no_browser", False),
                track=not getattr(args, "no_tracker", False))
        return 0

    if not cfg.records_dir.is_dir():
        print(f"Records folder not found: {cfg.records_dir}", file=sys.stderr)
        return 1

    if args.command == "watch":
        watch(cfg, args.interval)
        return 0

    try:
        result = import_records(cfg, args.rebuild)
    except PermissionError as e:
        print(e, file=sys.stderr)
        return 1
    for inst in cfg.instances:
        r = result.instances[inst.name]
        print(f"[{inst.name}] added {r.added}, updated {r.updated} ({r.total} runs); "
              f"wrote runs.csv, sessions.csv, stats.csv in {cfg.instance_dir(inst)}")
    for reason, count in result.ignored.items():
        print(f"Ignored {count} records ({reason})")
    for msg in result.unreadable:
        print(f"Could not read {msg}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
