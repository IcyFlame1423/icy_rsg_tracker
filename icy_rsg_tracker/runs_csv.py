"""runs.csv: one row per played world.

The CSV keeps its own copy of every run, so the history stays even if the
SpeedRunIGT records folder is cleared. New runs are merged in by run_id, then
the columns that depend on other runs (session_id, wall_resets_before) are
recalculated across the whole file.
"""

import csv
import json
import os
from datetime import datetime, timedelta

from .advancements import ADVANCEMENTS
from .hermes import DETAILS, ITEMS
from . import model
from .phases import COLUMNS as PHASE_COLUMNS, TIME_COLUMNS
from .records import SPLITS
from .timefmt import format_ms, parse_time

DATE_FORMAT = "%Y-%m-%d %H:%M:%S.%f"

BASE_COLUMNS = [
    "run_id",
    "date",               # local time the run ended (finished or reset)
    "session_id",
    "world_name",
    "world_number",
    "worlds_generated",   # how far this run pushed the highest world number (see compute_derived)
    "run_type",
    "seed",               # only if /seed was typed in the world (from the Hermes mod's play log)
    *SPLITS.keys(),       # nether, bastion, fortress, blind, stronghold, end
    "result",             # "finished" (beat the game) or "reset"
    "final_igt",
    "final_rta",
    "deaths",
    "deaths_with_respawn",     # respawned at a bed/anchor (death reset); from the game log
    "deaths_without_respawn",  # sent back to world spawn; from the game log
    "death_times",        # in-game time of each death, ";"-separated, "+" after a death reset
                          # (respawned at a bed/anchor); from the game log
    "cheats_from_rta",    # real time LAN was opened with cheats; later splits are left out
    # How many the run obtained (see hermes.ItemCounter); blank without a Hermes play log.
    *ITEMS,               # ender_pearls, blaze_rods, beds, respawn_anchors, fire_resistance, obsidian
    *DETAILS,             # where they went: blazes_killed, pearls_used, beds_lost, ... (see hermes.DETAILS)
    # From the play log and ghost (see phases.COLUMNS): distances in blocks (straight lines,
    # ignoring height), times as m:ss.mmm.
    *PHASE_COLUMNS,       # spawn_to_structures, ..., and the performance model's inputs (bucket_1-9, ...)
    "phases",             # JSON: the overworld, nether and stronghold sections (see phases.py)
    "play_log_key",       # the play log these came from (hermes.play_log_key): unchanged, it isn't read again
    "score",              # seconds lost against a top player on the same seed (model.py); finished runs only
]
COLUMNS = BASE_COLUMNS + ADVANCEMENTS


def format_date(dt):
    return dt.strftime(DATE_FORMAT)[:-3]  # keep milliseconds


def parse_date(text):
    return datetime.fromisoformat(text)  # much faster than strptime, same format


def run_to_row(run, death_counts=None, death_times=None, death_resets=None, play_log=None):
    """death_counts: (deaths, with_respawn, without_respawn) from deaths.death_columns;
    None values are left blank. Without it, only the record's death total is filled in.
    death_times: in-game ms of each death (deaths.death_times), or None if unknown.
    death_resets: for each death, whether it respawned at a bed/anchor (or None).
    play_log: what hermes.read_play_log found, or None without one."""
    row = dict.fromkeys(COLUMNS, "")
    resets = death_resets or [False] * len(death_times or [])
    row["death_times"] = ";".join(format_ms(t) + ("+" if r else "") for t, r in zip(death_times or [], resets))
    deaths, with_respawn, without_respawn = death_counts or (run.deaths, None, None)
    row.update({
        "deaths": str(deaths),
        "deaths_with_respawn": "" if with_respawn is None else str(with_respawn),
        "deaths_without_respawn": "" if without_respawn is None else str(without_respawn),
    })
    row.update(
        run_id=run.run_id,
        date=format_date(run.end_time),
        world_name=run.world_name,
        world_number="" if run.world_number is None else str(run.world_number),
        run_type=run.run_type,
        result="finished" if run.completed else "reset",
        final_igt=format_ms(run.final_igt),
        final_rta=format_ms(run.final_rta),
        cheats_from_rta=format_ms(run.cheats_from_rta),
    )
    if play_log:
        row.update(play_log_columns(play_log))
    for column, igt in run.splits.items():
        row[column] = format_ms(igt)
    for adv, igt in run.advancements.items():
        row[adv] = format_ms(igt)
    return row


def play_log_columns(play_log):
    """The runs.csv columns that come from a play log (hermes.read_play_log)."""
    phases = dict(play_log["phases"])
    numbers = phases.pop("columns", None) or {}
    columns = {"seed": play_log["seed"] or "", "phases": json.dumps(phases, separators=(",", ":"))}
    for item, count in {**play_log["items"], **play_log["details"]}.items():
        columns[item] = str(count)
    for name in PHASE_COLUMNS:
        value = numbers.get(name)
        columns[name] = format_ms(value) if name in TIME_COLUMNS else ("" if value is None else str(value))
    return columns


def load_rows(path):
    if not path.exists():
        return []
    with open(path, newline="", encoding="utf-8-sig") as f:
        return [{c: row.get(c) or "" for c in COLUMNS} for row in csv.DictReader(f)]


def _sort_key(row):
    return (row["date"], int(row["world_number"] or 0))


def active_ms(row, session_gap_minutes):
    """Real time spent in the run, for session timing.

    Normally final_rta. But if real time is more than a session gap past in-game
    time, the game sat paused (e.g. left overnight), so use in-game time instead.
    """
    rta = parse_time(row["final_rta"]) or 0
    igt = parse_time(row["final_igt"]) or 0
    if rta - igt > session_gap_minutes * 60_000:
        return igt
    return rta


def run_start(row, session_gap_minutes):
    return parse_date(row["date"]) - timedelta(milliseconds=active_ms(row, session_gap_minutes))


def compute_derived(rows, session_gap_minutes):
    """Sort rows by date and fill in session_id and worlds_generated.

    worlds_generated: SeedQueue numbers worlds when it creates them, but they get
    played from the wall in a different order, so world numbers jump around. Each run
    is credited with how far it pushes the highest world number seen so far (0 if it
    doesn't). Summed over any span of runs this is about how many worlds were
    generated, so wall resets ~= sum(worlds_generated) - runs played.
    """
    rows.sort(key=_sort_key)
    gap = timedelta(minutes=session_gap_minutes)
    session = 0
    prev_end = None
    highest = None
    for row in rows:
        end = parse_date(row["date"])
        start = run_start(row, session_gap_minutes)
        if prev_end is None or start - prev_end > gap:
            session += 1
        row["session_id"] = str(session)
        prev_end = end
        scored = model.score(row)
        row["score"] = "" if scored is None else f"{scored['score']:.1f}"

        row["worlds_generated"] = ""
        if row["world_number"]:
            number = int(row["world_number"])
            if highest is None or highest - number > COUNTER_RESTART_DROP:
                # First numbered world, or the counter restarted (e.g. a new instance):
                # count just this world.
                row["worlds_generated"] = "1"
                highest = number
            elif number > highest:
                row["worlds_generated"] = str(number - highest)
                highest = number
            else:
                row["worlds_generated"] = "0"  # generated earlier, played out of order
    return rows


# A drop in world number bigger than this is treated as a counter restart rather than
# an older world being played from the SeedQueue backlog (the largest seen is ~90).
COUNTER_RESTART_DROP = 1000


def save_rows(path, rows):
    """Write to a temp file and swap it in, so a crash never leaves half a CSV."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".csv.tmp")
    with open(tmp, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    try:
        os.replace(tmp, path)
    except PermissionError:
        os.remove(tmp)
        raise PermissionError(
            f"Could not write {path}. Is it open in Excel? Close it and try again."
        ) from None


def parse_death_times(text):
    """The death_times column -> ([in-game ms, ...], [death reset?, ...]), or (None, None)."""
    if not text:
        return None, None
    parts = text.split(";")
    return [parse_time(p.rstrip("+")) for p in parts], [p.endswith("+") for p in parts]
