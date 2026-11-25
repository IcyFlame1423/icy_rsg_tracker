"""Stats from runs.csv rows, written to sessions.csv and stats.csv.

compute_stats() works on any group of runs (one session, the last 7 days, all time),
so sessions.csv and stats.csv always report exactly the same stats.

Definitions:
- worlds_generated: sum of the per-run worlds_generated column (see runs_csv).
- wall_resets: worlds generated but never played (reset from the SeedQueue wall).
- total_resets: worlds generated that didn't finish (wall resets + played resets).
- time_span: for each session, first run start -> last run end, summed over sessions.
  Wall time before the first played world of a session isn't known, so isn't counted.
- playtime: time spent in worlds (sum of final_rta, except runs left paused for longer
  than the session gap count in-game time instead; see runs_csv.active_ms).
- <split>_rate: nether = share of played runs that entered the nether; every later
  split and finish = share of nether enters that reached it.
- <split>_avg / _median / _best: in-game time, over runs that reached the split.
"""

import csv
import statistics
from collections import defaultdict
from datetime import datetime, timedelta

from .records import SPLITS
from .runs_csv import active_ms, parse_date, run_start
from .timefmt import format_ms, parse_time

SPLIT_NAMES = list(SPLITS.keys())  # nether, bastion, fortress, blind, stronghold, end
TIMED = SPLIT_NAMES + ["finish"]
# Bastion and fortress can be done in either order, so progression uses the first and
# second structure entered instead, which keeps the order strict:
# nether -> structure1 -> structure2 -> blind -> stronghold -> end -> finish.
STRUCTURES = ["structure1", "structure2"]
PROGRESSION = ["nether", *STRUCTURES, "blind", "stronghold", "end", "finish"]

STAT_COLUMNS = [
    "runs_played", "worlds_generated", "wall_resets", "total_resets", "finished",
    "time_span", "playtime", "nethers_per_hour", "resets_per_nether",
]
for _name in TIMED:
    STAT_COLUMNS += [f"{_name}_count", f"{_name}_rate", f"{_name}_avg",
                     f"{_name}_median", f"{_name}_best"]

SESSION_COLUMNS = ["session_id", "start", "end"] + STAT_COLUMNS

# (column name in stats.csv, which runs) - "runs" is a function (rows, now) -> rows
WINDOWS = {
    "all_time": lambda rows, now: rows,
    "last_session": lambda rows, now: (
        [r for r in rows if r["session_id"] == rows[-1]["session_id"]] if rows else []),
    "last_7_days": lambda rows, now: _since(rows, now - timedelta(days=7)),
    "last_30_days": lambda rows, now: _since(rows, now - timedelta(days=30)),
}


def _since(rows, cutoff):
    return [r for r in rows if parse_date(r["date"]) >= cutoff]


def run_end(row):
    return parse_date(row["date"])


def split_time(row, name):
    """A run's in-game time for a split (nether..end, structure1/2, finish), or None."""
    if name == "finish":
        return parse_time(row["final_igt"]) if row["result"] == "finished" else None
    if name in STRUCTURES:
        entered = sorted(t for t in (parse_time(row["bastion"]), parse_time(row["fortress"]))
                         if t is not None)
        index = STRUCTURES.index(name)
        return entered[index] if len(entered) > index else None
    return parse_time(row[name])


def format_duration(td):
    """timedelta -> 'H:MM:SS'."""
    total = int(td.total_seconds())
    hours, rem = divmod(total, 3600)
    minutes, seconds = divmod(rem, 60)
    return f"{hours}:{minutes:02d}:{seconds:02d}"


def _by_session(rows):
    sessions = defaultdict(list)
    for row in rows:
        sessions[row["session_id"]].append(row)
    return sessions


def time_span(rows, gap):
    span = timedelta()
    for session_rows in _by_session(rows).values():
        start = min(run_start(r, gap) for r in session_rows)
        span += max(map(run_end, session_rows)) - start
    return span


def compute_raw(rows, gap):
    """Stats for a group of runs as numbers (times in ms, durations in seconds, rates 0-1).
    None where there's nothing to show. gap = session gap in minutes.

    {"runs_played", "worlds_generated", "wall_resets", "total_resets", "finished",
     "time_span_s", "playtime_s", "nethers_per_hour", "resets_per_nether",
     "splits": {name: {"count", "rate", "avg_ms", "median_ms", "best_ms"}}}
    for TIMED and STRUCTURES. rate: nether = of runs played, the rest = of nether enters.
    """
    played = len(rows)
    generated = sum(int(r["worlds_generated"] or 0) for r in rows)
    finished = sum(r["result"] == "finished" for r in rows)
    span_s = time_span(rows, gap).total_seconds() if rows else 0
    names = TIMED + STRUCTURES
    times = {name: [t for r in rows if (t := split_time(r, name)) is not None] for name in names}
    nethers = len(times["nether"])
    hours = span_s / 3600

    splits = {}
    for name in names:
        values = times[name]
        whole = played if name == "nether" else nethers
        splits[name] = {
            "count": len(values),
            "rate": len(values) / whole if whole else None,
            "avg_ms": round(statistics.fmean(values)) if values else None,
            "median_ms": round(statistics.median(values)) if values else None,
            "best_ms": min(values) if values else None,
        }
    return {
        "runs_played": played,
        "worlds_generated": generated,
        "wall_resets": max(generated - played, 0),
        "total_resets": max(generated - finished, 0),
        "finished": finished,
        "time_span_s": span_s,
        "playtime_s": sum(active_ms(r, gap) for r in rows) / 1000,
        "nethers_per_hour": nethers / hours if hours else None,
        "resets_per_nether": generated / nethers if nethers else None,
        "splits": splits,
    }


def compute_stats(rows, gap):
    """Stats for a group of runs, as {column: text} for the CSVs. Blank when there's
    nothing to show. gap = session gap in minutes."""
    stats = dict.fromkeys(STAT_COLUMNS, "")
    stats["runs_played"] = str(len(rows))
    if not rows:
        return stats
    raw = compute_raw(rows, gap)
    stats.update(
        worlds_generated=str(raw["worlds_generated"]),
        wall_resets=str(raw["wall_resets"]),
        total_resets=str(raw["total_resets"]),
        finished=str(raw["finished"]),
        time_span=format_duration(timedelta(seconds=raw["time_span_s"])),
        playtime=format_duration(timedelta(seconds=raw["playtime_s"])),
        nethers_per_hour="" if raw["nethers_per_hour"] is None else f"{raw['nethers_per_hour']:.2f}",
        resets_per_nether="" if raw["resets_per_nether"] is None else f"{raw['resets_per_nether']:.1f}",
    )
    for name in TIMED:
        s = raw["splits"][name]
        stats[f"{name}_count"] = str(s["count"])
        stats[f"{name}_rate"] = "" if s["rate"] is None else f"{100 * s['rate']:.1f}%"
        if s["count"]:
            stats[f"{name}_avg"] = format_ms(s["avg_ms"])
            stats[f"{name}_median"] = format_ms(s["median_ms"])
            stats[f"{name}_best"] = format_ms(s["best_ms"])
    return stats


def session_rows(rows, gap):
    out = []
    for session_id, runs in _by_session(rows).items():
        row = {
            "session_id": session_id,
            "start": min(run_start(r, gap) for r in runs).strftime("%Y-%m-%d %H:%M:%S"),
            "end": max(map(run_end, runs)).strftime("%Y-%m-%d %H:%M:%S"),
        }
        row.update(compute_stats(runs, gap))
        out.append(row)
    return out


def window_table(rows, gap, now=None):
    """stats.csv layout: one row per stat, one column per time window."""
    now = now or datetime.now()
    per_window = {name: compute_stats(select(rows, now), gap) for name, select in WINDOWS.items()}
    return [{"stat": stat, **{w: per_window[w][stat] for w in WINDOWS}} for stat in STAT_COLUMNS]


def _write_csv(path, columns, rows):
    tmp = path.with_suffix(".csv.tmp")
    with open(tmp, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)
    try:
        tmp.replace(path)
    except PermissionError:
        tmp.unlink()
        raise PermissionError(
            f"Could not write {path}. Is it open in Excel? Close it and try again.") from None


def write_stats(instance_dir, rows, session_gap_minutes, now=None):
    """rows must be sorted by date with session_id filled in (runs_csv.compute_derived)."""
    gap = session_gap_minutes
    _write_csv(instance_dir / "sessions.csv", SESSION_COLUMNS, session_rows(rows, gap))
    _write_csv(instance_dir / "stats.csv", ["stat", *WINDOWS], window_table(rows, gap, now))
