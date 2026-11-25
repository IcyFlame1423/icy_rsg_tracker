"""Classifying deaths from the Minecraft log.

A SpeedRunIGT record only counts deaths. Whether the player respawned at a bed/anchor
(a "death reset", done on purpose to restore health and hunger) or was sent back to
world spawn (an accidental death) is only visible in the game log:

    [16:51:28] [main/INFO]: [CHAT] Respawn point set
    [16:52:57] [Server thread #24882/INFO]: Player was shot by Piglin
    [16:53:00] [main/INFO]: [CHAT] You have no home bed or charged respawn anchor, or it was obstructed

So for each world (identified by its server thread: SeedQueue tags it "Server thread #<world
number>"; without SeedQueue there's one plain "Server thread", and each "joined the game"
starts the next world, named by the first "ServerLevel[<name>]" line after it):
- "Respawn point set" -> a spawn point is set.
- a death message    -> death WITH respawn if a spawn point is set, else WITHOUT.
- "You have no home bed..." on the respawn screen of a death (within RESPAWN_SCREEN_SECONDS,
  nothing else happening in between) -> the bed/anchor was gone, so that death was WITHOUT
  respawn after all. The same message also appears when leaving the End through the exit
  portal with no bed; then it isn't tied to a death. Either way the spawn point is cleared.
- advancements -> "activity": proves the player is alive, so a later "no home bed"
  message isn't from a death's respawn screen.
- "Local game hosted on port" -> opened to LAN; later deaths are flagged so they can be
  dropped when the run had cheats (like splits).

When each death happened in the run (death_times): the log has clock times, the record
has times since the run started. Advancements are in both ("has made the advancement
[We Need to Go Deeper]" in the log, its real time in the record), which lines them up.

Compressed logs (*.log.gz) never change, so each is parsed once and cached.
"""

import gzip
import json
import re
import statistics
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from .advancements import NAMES

LINE = re.compile(r"^\[(\d\d):(\d\d):(\d\d)\] \[([^\]]+)\]: (.*)$")
SERVER_THREAD = re.compile(r"^Server thread #(\d+)/")
PLAIN_SERVER_THREAD = "Server thread/"
JOINED = re.compile(r"^(\S+) joined the game$")
LEVEL_NAME = re.compile(r"ServerLevel\[(.+?)\]")
NOT_DEATHS = (
    "joined the game", "left the game", "lost connection", "has made the advancement",
    "has completed the challenge", "has reached the goal", "moved wrongly", "moved too quickly",
)
SPAWN_SET = "[CHAT] Respawn point set"
RESPAWN_FAILED = "[CHAT] You have no home bed or charged respawn anchor, or it was obstructed"
LAN_OPENED = "[CHAT] Local game hosted on port"
ACTIVITY = ("has made the advancement", "has completed the challenge", "has reached the goal")
ADVANCEMENT = re.compile(r"^has (?:made the advancement|completed the challenge|reached the goal) \[(.+)\]$")
RESPAWN_SCREEN_SECONDS = 30  # end fights can be under a minute

CACHE_VERSION = 4  # 3: event times are Unix seconds, advancement names and joins kept; 4: plain server thread


@dataclass
class Death:
    respawn: bool      # respawned at a bed/anchor
    after_lan: bool    # happened after the world was opened to LAN


@dataclass
class WorldDeaths:
    deaths: list = field(default_factory=list)
    events: list = field(default_factory=list)  # the raw [kind, seconds, ...] events


def parse_log_lines(lines):
    """Log lines -> {world name: [[event, seconds], ...]}.

    Events: "spawn", "death", "fail", "lan", "join", and "activity" (with the advancement's
    title as a third item). seconds counts from midnight of the log's first day (it keeps
    counting past midnight); scan_logs turns it into Unix time.
    """
    events = {}       # thread tag -> [[event, seconds]]
    names = {}        # thread tag -> world name
    players = {}      # thread tag -> player name
    current = None    # thread tag of the world the player is in
    day_offset, last_seconds = 0, 0
    plain_worlds = 0  # worlds seen on a plain (unnumbered) server thread so far
    for line in lines:
        m = LINE.match(line)
        if not m:
            continue
        hh, mm, ss, thread, msg = m.groups()
        seconds = int(hh) * 3600 + int(mm) * 60 + int(ss) + day_offset
        if seconds < last_seconds - 12 * 3600:  # clock wrapped past midnight
            day_offset += 86400
            seconds += 86400
        last_seconds = seconds

        def add(tag, kind, *extra):
            events.setdefault(tag, []).append([kind, seconds, *extra])

        t = SERVER_THREAD.match(thread)
        if t or thread.startswith(PLAIN_SERVER_THREAD):
            if t:
                tag = t.group(1)
            else:  # one world at a time: each join starts the next one
                if JOINED.match(msg):
                    plain_worlds += 1
                tag = f"plain-{plain_worlds}"
            if tag not in names and (lvl := LEVEL_NAME.search(msg)):
                names[tag] = lvl.group(1)
            if j := JOINED.match(msg):
                players[tag] = j.group(1)
                current = tag
                add(tag, "join")
            elif tag in players and msg.startswith(players[tag] + " "):
                rest = msg[len(players[tag]) + 1:]
                if rest == "left the game":
                    if current == tag:
                        current = None
                elif rest.startswith(ACTIVITY):
                    a = ADVANCEMENT.match(rest)
                    add(tag, "activity", *([a.group(1)] if a else []))
                elif not rest.startswith(NOT_DEATHS):
                    add(tag, "death")
        elif current is not None and thread.startswith("main/"):
            if msg == SPAWN_SET:
                add(current, "spawn")
            elif msg == RESPAWN_FAILED:
                add(current, "fail")
            elif msg.startswith(LAN_OPENED):
                add(current, "lan")
    return {names[tag]: evs for tag, evs in events.items() if tag in names}


def classify(events):
    spawn = lan = False
    deaths = []
    previous = None  # the event before this one
    for kind, seconds, *_ in events:
        if kind == "spawn":
            spawn = True
        elif kind == "death":
            deaths.append(Death(respawn=spawn, after_lan=lan))
        elif kind == "fail":
            on_respawn_screen = (previous is not None and previous[0] == "death"
                                 and seconds - previous[1] <= RESPAWN_SCREEN_SECONDS)
            if on_respawn_screen:
                deaths[-1].respawn = False
            spawn = False
        elif kind == "lan":
            lan = True
        previous = (kind, seconds)
    return WorldDeaths(deaths, events)


def _log_sort_key(path):
    """'2026-11-24-5.log.gz' -> ('2026-11-24', 5); latest.log sorts last."""
    if path.name == "latest.log":
        return ("9999", 0)
    date, _, n = path.name.removesuffix(".log.gz").rpartition("-")
    return (date, int(n) if n.isdigit() else 0)


def _read_lines(path):
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding="utf-8", errors="replace") as f:
        # Only lines that can matter, to keep parsing fast.
        return [line.rstrip("\n") for line in f
                if "Server thread" in line or "[CHAT]" in line]


def scan_logs(logs_dir, cache_path=None):
    """{world name: WorldDeaths} from every log in logs_dir."""
    if not logs_dir or not logs_dir.is_dir():
        return {}
    cache = {}
    if cache_path and cache_path.exists():
        try:
            cache = json.loads(cache_path.read_text(encoding="utf-8"))
            if cache.get("version") != CACHE_VERSION:
                cache = {}
        except ValueError:
            cache = {}
    files = cache.setdefault("files", {})
    cache["version"] = CACHE_VERSION

    merged = {}
    changed = False
    paths = sorted([*logs_dir.glob("*.log.gz"), logs_dir / "latest.log"], key=_log_sort_key)
    for path in paths:
        if not path.exists():
            continue
        stat = path.stat()
        key = [stat.st_size, stat.st_mtime]
        entry = files.get(path.name)
        if path.suffix == ".gz" and entry and entry["key"] == key:
            worlds = entry["worlds"]
        else:
            try:
                worlds = parse_log_lines(_read_lines(path))
            except (OSError, EOFError) as e:  # e.g. a truncated .gz
                print(f"Could not read log {path.name}: {e}")
                continue
            start = _log_day_start(path, stat.st_mtime, worlds)
            for evs in worlds.values():
                for ev in evs:
                    ev[1] += start
            if path.suffix == ".gz":
                files[path.name] = {"key": key, "worlds": worlds}
                changed = True
        for name, events in worlds.items():
            merged.setdefault(name, []).extend(events)

    if cache_path and changed:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(cache), encoding="utf-8")
    return {name: classify(events) for name, events in merged.items()}


def _log_day_start(path, mtime, worlds):
    """Unix time of midnight on the log's first day. Rotated logs are named by date
    (2026-11-21-2.log.gz); latest.log is dated by when it was last written."""
    try:
        day = datetime.strptime(path.name[:10], "%Y-%m-%d")
    except ValueError:
        last = max((ev[1] for evs in worlds.values() for ev in evs), default=0)
        first_day = datetime.fromtimestamp(mtime) - timedelta(seconds=last)
        day = datetime.combine(first_day.date(), datetime.min.time())
    return day.timestamp()


def death_times(world_deaths, record):
    """In-game time (ms) of each death in the run, oldest first, or None if they can't be
    placed (the log's deaths don't match the record's count, or nothing lines them up).

    The log's clock time of each advancement minus its real time in the record gives the
    clock time the run started (the median, to shrug off a stray second). A death's real
    time then converts to in-game time using the record's nearest earlier event, since
    in-game time lags real time by however long was spent paused or loading.
    """
    if world_deaths is None:
        return None
    events = world_deaths.events
    deaths_at = [ev[1] for ev in events if ev[0] == "death"]
    if not deaths_at or len(deaths_at) != _record_deaths(record):
        return None
    by_title = {}
    for adv_id, adv in (record.get("advancements") or {}).items():
        name = NAMES.get(adv_id.removeprefix("minecraft:"))
        if name and adv.get("complete") and adv.get("rta") is not None:
            by_title[name] = adv
    starts = [ev[1] - by_title[ev[2]]["rta"] / 1000 for ev in events
              if ev[0] == "activity" and len(ev) > 2 and ev[2] in by_title]
    if starts:
        start = statistics.median(starts)
    else:
        joins = [ev[1] for ev in events if ev[0] == "join"]
        if not joins:
            return None
        start = joins[0]  # the timer starts about when you join
    # (real ms, in-game ms) pairs from the record, to convert real time to in-game time.
    points = sorted((p["rta"], p["igt"]) for p in [*(record.get("timelines") or []),
                                                    *(record.get("advancements") or {}).values()]
                    if p.get("rta") is not None and p.get("igt") is not None)
    out = []
    for t in deaths_at:
        rta = max(0, round((t - start) * 1000))
        lag = next((r - i for r, i in reversed(points) if r <= rta), 0)
        out.append(max(0, rta - lag))
    return out


def _record_deaths(record):
    return sum(p.get("stats", {}).get("minecraft:custom", {}).get("minecraft:deaths", 0)
               for p in (record.get("stats") or {}).values())


def death_columns(record_deaths, world_deaths, cheats):
    """Values for the deaths / deaths_with_respawn / deaths_without_respawn columns.

    record_deaths: death count from the SpeedRunIGT record (always available).
    world_deaths: WorldDeaths from the log, or None if the log doesn't have this world.
    cheats: the run had cheats turned on via LAN, so deaths after that don't count.
    The respawn split is left blank unless the log saw exactly as many deaths as the
    record, so a missing or partial log never gives wrong numbers.
    """
    if record_deaths == 0:
        return 0, 0, 0
    if world_deaths is None or len(world_deaths.deaths) != record_deaths:
        return record_deaths, None, None
    counted = [d for d in world_deaths.deaths if not (cheats and d.after_lan)]
    with_respawn = sum(d.respawn for d in counted)
    return len(counted), with_respawn, len(counted) - with_respawn
