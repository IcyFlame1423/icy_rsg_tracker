"""What the app's API serves: runs.csv rows, filtered to a time window, with stats.

Everything is computed from runs.csv with the same code that writes stats.csv and
sessions.csv (stats.compute_raw), so the app and the CSVs always agree.
"""

import bisect
import json
import statistics
import threading
from collections import defaultdict
from datetime import datetime, time, timedelta

from .. import runs_csv
from ..resources import resources
from ..advancements import ADVANCEMENTS, NAMES
from ..records import SPLITS
from ..stats import PROGRESSION, STRUCTURES, compute_raw, run_end, run_start, split_time
from ..timefmt import parse_time

SPLIT_NAMES = list(SPLITS)  # nether ... end

WINDOWS = ("last_session", "today", "7d", "30d", "1y", "all", "custom", "session")


class BadRequest(ValueError):
    """An API request with invalid parameters (-> HTTP 400)."""


class DataStore:
    """Rows of each instance's runs.csv, re-read only when the file changes."""

    def __init__(self, cfg):
        self.cfg = cfg
        self._cache = {}  # instance name -> (mtime, rows)
        self._lock = threading.Lock()

    def instance(self, name):
        for inst in self.cfg.instances:
            if inst.name == name:
                return inst
        raise BadRequest(f"unknown instance {name!r}")

    def rows(self, instance_name):
        path = self.cfg.runs_csv(self.instance(instance_name))
        try:
            mtime = path.stat().st_mtime
        except FileNotFoundError:
            return []
        with self._lock:
            cached = self._cache.get(instance_name)
            if cached and cached[0] == mtime:
                return cached[1]
            rows = runs_csv.load_rows(path)  # already sorted by date, session_id filled in
            self._cache[instance_name] = (mtime, rows)
            return rows


def _parse_day(text, name):
    try:
        return datetime.strptime(text, "%Y-%m-%d")
    except (TypeError, ValueError):
        raise BadRequest(f"{name} must be a date like 2026-11-24") from None


def select_window(rows, window, start=None, end=None, now=None, session=None):
    """Runs in a time window, by when each run ended.

    window: last_session | today | 7d | 30d | 1y | all
            | custom (start/end: YYYY-MM-DD, inclusive) | session (session: its number).
    """
    now = now or datetime.now()
    if window == "all":
        return rows
    if window == "session":
        if not str(session or "").isdigit():
            raise BadRequest("session must be a session number")
        return [r for r in rows if r["session_id"] == str(int(session))]
    if window == "last_session":
        if not rows:
            return []
        last = rows[-1]["session_id"]
        return [r for r in rows if r["session_id"] == last]
    if window == "today":
        lo, hi = datetime.combine(now.date(), time.min), None
    elif window == "7d":
        lo, hi = now - timedelta(days=7), None
    elif window == "30d":
        lo, hi = now - timedelta(days=30), None
    elif window == "1y":
        lo, hi = now - timedelta(days=365), None
    elif window == "custom":
        lo = _parse_day(start, "start")
        hi = _parse_day(end, "end") + timedelta(days=1)
        if hi <= lo:
            raise BadRequest("end must not be before start")
    else:
        raise BadRequest(f"window must be one of {', '.join(WINDOWS)}")
    return [r for r in rows if run_end(r) >= lo and (hi is None or run_end(r) < hi)]


def _session_summaries(rows, gap):
    """Per-session numbers (trend charts, sessions table), oldest first."""
    sessions = defaultdict(list)
    for row in rows:
        sessions[row["session_id"]].append(row)
    out = []
    for session_id, runs in sessions.items():
        raw = compute_raw(runs, gap)
        times = [{name: split_time(r, name) for name in PROGRESSION} for r in runs]
        segment_avg = {}  # average time from the previous split, for runs that reached both
        for prev, name in zip(PROGRESSION, PROGRESSION[1:]):
            segment_avg[name] = _avg([t[name] - t[prev] for t in times
                                      if t[name] is not None and t[prev] is not None])
        out.append({
            "session_id": int(session_id),
            "start": min(run_start(r, gap) for r in runs).isoformat(timespec="seconds"),
            "end": max(map(run_end, runs)).isoformat(timespec="seconds"),
            "runs_played": raw["runs_played"],
            "wall_resets": raw["wall_resets"],
            "total_resets": raw["total_resets"],
            "resets_per_nether": raw["resets_per_nether"],
            "finished": raw["finished"],
            "time_span_s": raw["time_span_s"],
            "playtime_s": raw["playtime_s"],
            "nethers_per_hour": raw["nethers_per_hour"],
            # {split: {"count", "avg_ms", "best_ms", "segment_avg_ms"}} for nether ... finish,
            # structure1/2. segment_avg_ms: from the previous split in PROGRESSION (None for the
            # nether, and bastion/fortress, which aren't in it).
            "splits": {name: {"count": s["count"], "avg_ms": s["avg_ms"], "best_ms": s["best_ms"],
                              "segment_avg_ms": segment_avg.get(name)}
                       for name, s in raw["splits"].items()},
        })
    out.sort(key=lambda s: s["session_id"])
    return out


def summary(store, instance_name, window, start=None, end=None, now=None, session=None):
    """Everything the dashboard shows for one instance and time window."""
    gap = store.cfg.session_gap_minutes
    all_rows = store.rows(instance_name)
    rows = select_window(all_rows, window, start, end, now, session)
    return {
        "instance": instance_name,
        "window": window,
        "total_runs": len(all_rows),
        "first_run": rows[0]["date"] if rows else None,
        "last_run": rows[-1]["date"] if rows else None,
        "stats": compute_raw(rows, gap),
        "sessions": _session_summaries(rows, gap),
    }


def sessions(store, instance_name, window, start=None, end=None, now=None, session=None):
    """The sessions table: one entry per session with runs in the window, newest first."""
    gap = store.cfg.session_gap_minutes
    rows = select_window(store.rows(instance_name), window, start, end, now, session)
    return {"instance": instance_name, "window": window,
            "sessions": _session_summaries(rows, gap)[::-1]}


def _int(text):
    return int(text) if text else None


def run_json(row):
    """A runs.csv row as JSON: times in ms (None if not reached), counts as ints."""
    return {
        "run_id": row["run_id"],
        "date": row["date"].replace(" ", "T"),
        "session_id": int(row["session_id"]),
        "world_name": row["world_name"],
        "world_number": _int(row["world_number"]),
        "worlds_generated": _int(row["worlds_generated"]),
        "result": row["result"],
        "splits": {name: parse_time(row[name]) for name in SPLIT_NAMES},
        "final_igt": parse_time(row["final_igt"]),
        "final_rta": parse_time(row["final_rta"]),
        "deaths": _int(row["deaths"]),
        "deaths_with_respawn": _int(row["deaths_with_respawn"]),
        "deaths_without_respawn": _int(row["deaths_without_respawn"]),
        # In-game ms of each death, or None if the log couldn't place them.
        "death_times": runs_csv.parse_death_times(row["death_times"])[0],
        "cheats_from_rta": parse_time(row["cheats_from_rta"]),
        "advancements": {name: parse_time(row[name]) for name in ADVANCEMENTS if row[name]},
    }


def runs(store, instance_name, window, start=None, end=None, now=None, session=None):
    """Runs in the window (oldest first), plus all-time personal bests for each split."""
    all_rows = store.rows(instance_name)
    rows = select_window(all_rows, window, start, end, now, session)
    pbs = {}
    for row in all_rows:
        for name in [*SPLIT_NAMES, *STRUCTURES, "finish"]:
            t = split_time(row, name)
            if t is not None and (name not in pbs or t < pbs[name]["ms"]):
                pbs[name] = {"ms": t, "run_id": row["run_id"]}
    # Best in-game time for each advancement any run has got.
    advancement_pbs = {}
    # Best time from one split to a later split or advancement ("adv:<id>"):
    # {from split: {target: {ms, run_id}}}, from runs that reached both. An advancement can come
    # before the split: its time is then negative.
    from_pbs = {name: {} for name in PROGRESSION[:-1]}
    for row in all_rows:
        splits = [(name, t) for name in PROGRESSION if (t := split_time(row, name)) is not None]
        advs = [(f"adv:{name}", parse_time(row[name])) for name in ADVANCEMENTS if row[name]]
        for name, t in advs:
            if name[4:] not in advancement_pbs or t < advancement_pbs[name[4:]]["ms"]:
                advancement_pbs[name[4:]] = {"ms": t, "run_id": row["run_id"]}
        for i, (start, s) in enumerate(splits):
            if start == "finish":
                continue
            for target, t in splits[i + 1:] + advs:
                best = from_pbs[start].get(target)
                if best is None or t - s < best["ms"]:
                    from_pbs[start][target] = {"ms": t - s, "run_id": row["run_id"]}
    return {"instance": instance_name, "window": window, "total_runs": len(all_rows),
            "runs": [run_json(r) for r in rows], "pbs": pbs, "from_pbs": from_pbs,
            "advancement_pbs": advancement_pbs,
            "advancements": [{"id": a, "name": NAMES[a]} for a in ADVANCEMENTS]}


def _avg(values):
    return round(statistics.fmean(values)) if values else None


def _baseline(rows, times, run):
    """How a run compares with a group of runs. times: {run_id: {split: ms}} for rows."""
    this = times[run["run_id"]]
    splits = {}
    for i, key in enumerate(PROGRESSION):
        values = sorted(t[key] for t in (times[r["run_id"]] for r in rows) if t[key] is not None)
        entry = {
            "count": len(values),
            "avg_ms": _avg(values),
            "median_ms": round(statistics.median(values)) if values else None,
            "best_ms": values[0] if values else None,
            # 1 = fastest of the group; ties share the better rank.
            "rank": bisect.bisect_left(values, this[key]) + 1 if this[key] is not None else None,
            "segment_avg_ms": None,
            "segment_best_ms": None,
        }
        if i:  # time from the previous split, for runs that reached both
            prev = PROGRESSION[i - 1]
            segments = [t[key] - t[prev] for t in (times[r["run_id"]] for r in rows)
                        if t[key] is not None and t[prev] is not None]
            entry["segment_avg_ms"] = _avg(segments)
            entry["segment_best_ms"] = min(segments) if segments else None
        splits[key] = entry
    advancements = {}
    for name in ADVANCEMENTS:
        if run[name]:
            values = [parse_time(r[name]) for r in rows if r[name]]
            advancements[name] = {"count": len(values), "avg_ms": _avg(values), "best_ms": min(values)}
    return {"runs": len(rows), "splits": splits, "advancements": advancements}


def run_detail(store, instance_name, run_id):
    """One run with its split times, and how they compare with all runs and its session."""
    rows = store.rows(instance_name)
    index = next((i for i, r in enumerate(rows) if r["run_id"] == run_id), None)
    if index is None:
        raise BadRequest("There's no run with that id (a rebuild may have removed it).")
    row = rows[index]
    times = {r["run_id"]: {key: split_time(r, key) for key in PROGRESSION} for r in rows}
    session = [r for r in rows if r["session_id"] == row["session_id"]]
    # Which structure was entered first (structure 1) and second.
    entered = sorted((t, name) for name in ("bastion", "fortress") if (t := parse_time(row[name])) is not None)
    try:  # resources come from the record's item statistics, which runs.csv doesn't keep
        record = json.loads((store.cfg.records_dir / f"{run_id}.json").read_text(encoding="utf-8"))
        run_resources = resources(record, *runs_csv.parse_death_times(row["death_times"]))
    except (OSError, ValueError):
        run_resources = None  # record deleted or unreadable
    nethers = [i for i, r in enumerate(rows) if r["nether"]]
    before = [i for i in nethers if i < index]
    after = [i for i in nethers if i > index]
    return {
        "instance": instance_name,
        "run": run_json(row),
        "times": times[run_id],
        "structures": [name for _, name in entered],
        "session": {"id": int(row["session_id"]), "position": session.index(row) + 1, "runs": len(session)},
        "previous_nether_run": rows[before[-1]]["run_id"] if before else None,
        "next_nether_run": rows[after[0]]["run_id"] if after else None,
        "advancement_names": {name: NAMES[name] for name in ADVANCEMENTS if row[name]},
        "resources": run_resources,
        "compare": {"all": _baseline(rows, times, row), "session": _baseline(session, times, row)},
    }
