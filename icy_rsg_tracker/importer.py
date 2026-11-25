"""Adding SpeedRunIGT records to each instance's runs.csv.

Every instance writes to the same records folder, so each record is matched to an
instance by world name (see config.Instance). Records matching no instance are ignored.

A record is (re)read if it is new, or if it changed after that instance's runs.csv was
last written. That covers a world that was still being played at the last import: its
row is replaced with the newer data. (latest_world.json can't be used to tell which
world is in progress: with SeedQueue it isn't updated when you play worlds from the wall.)
"""

import os
import shutil
from dataclasses import dataclass, field
from pathlib import Path

from . import deaths, runs_csv, stats
from .records import load_record, read_record_json

# Why a record isn't tracked
OTHER_INSTANCE = "from other instances"
SET_SEED = "set seed"
CHEATS_AT_START = "cheats on from world creation"


@dataclass
class InstanceResult:
    added: int = 0
    updated: int = 0
    total: int = 0
    changed_ids: list = field(default_factory=list)  # run_ids added or updated
    rows: list = field(default_factory=list, repr=False)  # all rows, sorted by date


@dataclass
class ImportResult:
    instances: dict = field(default_factory=dict)  # instance name -> InstanceResult
    ignored: dict = field(default_factory=dict)    # reason -> count of records
    unreadable: list = field(default_factory=list)


class _InstanceState:
    def __init__(self, path, rebuild):
        self.path = path
        if rebuild and path.exists():
            shutil.copy2(path, path.with_suffix(".csv.bak"))
        existing = [] if rebuild else runs_csv.load_rows(path)
        self.by_id = {row["run_id"]: row for row in existing}
        self.last_written = path.stat().st_mtime if (path.exists() and not rebuild) else 0
        self.result = InstanceResult()
        self.world_deaths = None  # {world name: WorldDeaths} from the game logs, read lazily


def import_records(cfg, rebuild=False, ignored=None, write_unchanged=True):
    """Import new/changed records for every instance.

    ignored: optional dict {run_id: (mtime, reason)} kept between calls (by the watcher)
        so records that aren't tracked aren't re-read until they change.
    write_unchanged: rewrite files for instances with no changed runs too (keeps the
        date-based stats windows like last_7_days current).
    """
    states = {inst.name: _InstanceState(cfg.runs_csv(inst), rebuild) for inst in cfg.instances}
    ignored = {} if (ignored is None or rebuild) else ignored
    result = ImportResult()

    with os.scandir(cfg.records_dir) as entries:
        records = [(e.name[:-5], e.stat().st_mtime, Path(e.path))
                   for e in entries if e.name.endswith(".json")]

    for run_id, mtime, record_path in records:
        # Skip records already handled and unchanged since, without opening them.
        if run_id in ignored and ignored[run_id][0] == mtime:
            continue
        owner = next((s for s in states.values() if run_id in s.by_id), None)
        if owner and mtime <= owner.last_written:
            continue
        try:
            run = load_record(record_path)
        except (OSError, ValueError, KeyError) as e:
            # Most likely SpeedRunIGT is writing the file right now; it gets picked up next time.
            result.unreadable.append(f"{record_path.name}: {e}")
            continue

        instance = cfg.instance_for(run.world_name)
        reason = None
        if instance is None:
            reason = OTHER_INSTANCE
        elif run.run_type != "random_seed" and not cfg.include_set_seed:
            reason = SET_SEED
        elif run.cheats_at_start:
            reason = CHEATS_AT_START
        if reason:
            ignored[run_id] = (mtime, reason)
            if owner:
                owner.by_id.pop(run_id)  # tracked before, but not any more
                owner.result.changed_ids.append(run_id)
            continue

        ignored.pop(run_id, None)
        state = states[instance.name]
        if run_id in state.by_id:
            state.result.updated += 1
        else:
            state.result.added += 1
        state.result.changed_ids.append(run_id)
        death_counts = death_times = death_resets = None
        if run.deaths:
            if state.world_deaths is None:  # read the logs once per import, only if needed
                state.world_deaths = deaths.scan_logs(
                    instance.logs_dir, cfg.instance_dir(instance) / "log_cache.json")
            world = state.world_deaths.get(run.world_name)
            death_counts = deaths.death_columns(run.deaths, world, run.cheats_from_rta is not None)
            try:
                death_times = deaths.death_times(world, read_record_json(record_path))
            except (OSError, ValueError):
                death_times = None
            if death_times is not None:  # the log's deaths match the record's, one for one
                death_resets = [d.respawn for d in world.deaths]
        state.by_id[run_id] = runs_csv.run_to_row(run, death_counts, death_times, death_resets)

    for name, state in states.items():
        rows = list(state.by_id.values())
        runs_csv.compute_derived(rows, cfg.session_gap_minutes)
        if write_unchanged or state.result.changed_ids or rebuild:
            runs_csv.save_rows(state.path, rows)
            stats.write_stats(state.path.parent, rows, cfg.session_gap_minutes)
        state.result.total = len(rows)
        state.result.rows = rows
        result.instances[name] = state.result

    for _, reason in ignored.values():
        result.ignored[reason] = result.ignored.get(reason, 0) + 1
    return result
