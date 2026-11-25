"""Live mode: keep the CSVs up to date while you play.

Checks the records folder every few seconds (a directory listing, ~10 ms). When a
record is added or changes, imports it, rewrites that instance's CSVs and prints a line
for each run. Runs at below-normal CPU priority so it never competes with Minecraft.
"""

import os
import sys
import threading
import time
from datetime import datetime

from .importer import import_records
from .records import SPLITS
from .stats import compute_stats


def lower_priority():
    if sys.platform == "win32":
        import ctypes
        BELOW_NORMAL_PRIORITY_CLASS = 0x4000
        kernel32 = ctypes.windll.kernel32
        kernel32.SetPriorityClass(kernel32.GetCurrentProcess(), BELOW_NORMAL_PRIORITY_CLASS)
    else:
        os.nice(10)


def snapshot(records_dir):
    """(number of records, newest modification time): changes whenever a record is
    added, rewritten or deleted."""
    count, newest = 0, 0.0
    with os.scandir(records_dir) as entries:
        for e in entries:
            if e.name.endswith(".json"):
                count += 1
                newest = max(newest, e.stat().st_mtime)
    return count, newest


def describe_run(row):
    """'#24660 reset at 4:12.300 | nether 2:33.100 | bastion 3:40.020'"""
    name = f"#{row['world_number']}" if row["world_number"] else row["world_name"]
    parts = [f"{name} {row['result']} at {row['final_igt']}"]
    parts += [f"{split} {row[split]}" for split in SPLITS if row[split]]
    if row["cheats_from_rta"]:
        parts.append(f"cheats (LAN) from {row['cheats_from_rta']} RTA")
    return " | ".join(parts)


def describe_session(rows, gap):
    session_id = rows[-1]["session_id"]
    s = compute_stats([r for r in rows if r["session_id"] == session_id], gap)
    text = (f"session {session_id}: {s['runs_played']} played, {s['wall_resets']} wall resets, "
            f"{s['nether_count']} nethers")
    if s["nethers_per_hour"]:
        text += f" ({s['nethers_per_hour']}/h)"
    if s["nether_avg"]:
        text += f", avg nether {s['nether_avg']}"
    return text


def report(result, cfg, out):
    stamp = datetime.now().strftime("%H:%M:%S")
    for name, r in result.instances.items():
        if not r.changed_ids:
            continue
        by_id = {row["run_id"]: row for row in r.rows}
        for run_id in r.changed_ids:
            row = by_id.get(run_id)
            if row:
                out(f"{stamp} [{name}] {describe_run(row)}")
        if r.rows:
            out(f"{stamp} [{name}]   {describe_session(r.rows, cfg.session_gap_minutes)}")
    for msg in result.unreadable:
        out(f"{stamp} could not read {msg} (will retry)")


class Tracker:
    """Keeps the CSVs updated. Used by the console `watch` command and by the app,
    which runs it in a background thread and reads its status."""

    def __init__(self, cfg, interval=None, out=print):
        self.cfg = cfg
        self._interval = interval  # None: use cfg.watch_interval_seconds (can change live)
        self.out = out
        self.ignored = {}  # records that aren't tracked, so they aren't re-read every time
        self.version = 0   # goes up whenever the CSVs change; the app refreshes on it
        self.last_import = None  # datetime of the last import that changed something
        self.warning = None      # e.g. a CSV is open in Excel, or the records folder is missing
        self.lock = threading.RLock()  # one import (or settings change) at a time
        self._snap = None
        self._retry = False
        self._started = False

    @property
    def interval(self):
        return self._interval or self.cfg.watch_interval_seconds

    def _import(self, write_unchanged, rebuild=False):
        with self.lock:
            return import_records(self.cfg, rebuild=rebuild, ignored=self.ignored,
                                  write_unchanged=write_unchanged)

    def _records_missing(self):
        if self.cfg.records_dir.is_dir():
            return False
        message = f"SpeedRunIGT records folder not found: {self.cfg.records_dir}. Set it in Settings."
        if self.warning != message:
            self.out(message)
        self.warning = message
        return True

    def start(self):
        """First import: picks up everything since the tracker last ran."""
        if self._records_missing():
            return
        self.out(f"Watching {self.cfg.records_dir} (every {self.interval:g}s).")
        self._snap = snapshot(self.cfg.records_dir)
        try:
            result = self._import(write_unchanged=True)
        except PermissionError as e:
            self.warning = str(e)
            self._retry = True
            self.out(str(e))
            return
        self._started = True
        self.warning = None
        self.version += 1
        self.last_import = datetime.now()
        for name, r in result.instances.items():
            self.out(f"[{name}] {r.total} runs; {r.added} new, {r.updated} updated since last time "
                     f"-> {self.cfg.output_dir / name}")
            if r.rows:
                self.out(f"[{name}]   last {describe_session(r.rows, self.cfg.session_gap_minutes)}")

    def check(self):
        """One check for new or changed records; imports them if there are any."""
        if not self._started:
            return self.start()
        if self._records_missing():
            return
        new_snap = snapshot(self.cfg.records_dir)
        if new_snap == self._snap and not self._retry:
            return
        try:
            result = self._import(write_unchanged=False)
        except PermissionError as e:
            if self.warning != str(e):
                self.out(f"{datetime.now():%H:%M:%S} {e} Retrying...")
            self.warning = str(e)
            self._retry = True
            return
        # Take the snapshot from *before* the import as the new baseline, so a record
        # written during the import is still picked up next time.
        self._snap = new_snap
        self._retry = bool(result.unreadable)
        self.warning = None
        if any(r.changed_ids for r in result.instances.values()):
            self.version += 1
            self.last_import = datetime.now()
        report(result, self.cfg, self.out)

    def settings_changed(self):
        """Settings were changed: forget cached decisions and re-import everything, so
        new instances/patterns and a new session gap take effect."""
        with self.lock:
            self.ignored.clear()
            self._started = False
            self._snap = None
        self.check()
        self.version += 1

    def rebuild(self):
        """Rebuild every instance's runs.csv from the records folder."""
        with self.lock:
            if self._records_missing():
                raise FileNotFoundError(self.warning)
            self.ignored.clear()
            result = self._import(write_unchanged=True, rebuild=True)
            self._snap = snapshot(self.cfg.records_dir)
            self._started = True
            self.warning = None
        self.version += 1
        self.last_import = datetime.now()
        return result

    def run(self, stop=None):
        """Loop until `stop` (a threading.Event) is set, or forever if it's None."""
        self.start()
        while True:
            if stop is None:
                time.sleep(self.interval)
            elif stop.wait(self.interval):
                return
            self.check()


def watch(cfg, interval=None, out=print):
    lower_priority()
    out("Press Ctrl+C to stop.")
    try:
        Tracker(cfg, interval, out).run()
    except KeyboardInterrupt:
        out("Stopped.")
