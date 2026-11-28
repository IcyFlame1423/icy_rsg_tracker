"""Reading SpeedRunIGT record files (speedrunigt/records/<uuid>.json)."""

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .advancements import ADVANCEMENT_SET

# Split column -> SpeedRunIGT timeline event name.
SPLITS = {
    "nether": "enter_nether",
    "bastion": "enter_bastion",
    "fortress": "enter_fortress",
    "blind": "nether_travel_blind",
    "stronghold": "enter_stronghold",
    "end": "enter_end",
}

_WORLD_NUMBER = re.compile(r"#(\d+)$")


@dataclass
class Run:
    run_id: str
    world_name: str
    world_number: int | None
    end_time: datetime        # when the record was saved (run finished or reset)
    run_type: str
    completed: bool
    final_igt: int
    final_rta: int
    # Real time when cheats were turned on by opening to LAN, or None.
    # Splits/advancements reached after this are left out.
    cheats_from_rta: int | None = None
    # Cheats were on from the start (world created with cheats); the run isn't legit.
    cheats_at_start: bool = False
    # Created as a survival world (not creative, spectator, adventure or hardcore).
    survival: bool = True
    deaths: int = 0  # from the record's stats (includes any after cheats were turned on)
    splits: dict = field(default_factory=dict)        # split column -> igt ms
    advancements: dict = field(default_factory=dict)  # "story/iron_tools" -> igt ms

    @property
    def start_time(self):
        return datetime.fromtimestamp(self.end_time.timestamp() - self.final_rta / 1000)


def parse_world_number(world_name):
    """'Random Speedrun #24609' -> 24609. Other names -> None."""
    m = _WORLD_NUMBER.search(world_name or "")
    return int(m.group(1)) if m else None


def parse_record(data, run_id):
    """Turn a record's JSON into a Run."""
    # is_cheat_allowed is also set when the world is opened to LAN with cheats.
    # open_lan is the real time (ms) when that happened.
    cheats = bool(data.get("is_cheat_allowed"))
    open_lan = data.get("open_lan")
    cheats_from_rta = open_lan if (cheats and open_lan is not None) else None

    def legit(entry):
        return cheats_from_rta is None or entry.get("rta", 0) < cheats_from_rta

    splits = {}
    for timeline in data.get("timelines", []):
        if not legit(timeline):
            continue
        for column, event in SPLITS.items():
            # Keep the first time an event happens.
            if timeline.get("name") == event and column not in splits:
                splits[column] = timeline["igt"]
    _fix_home_portal_blind(splits, data, legit)

    advancements = {}
    for adv_id, adv in data.get("advancements", {}).items():
        if not (adv.get("complete") and adv.get("is_advancement") and legit(adv)):
            continue
        name = adv_id.removeprefix("minecraft:")
        if name in ADVANCEMENT_SET:
            advancements[name] = adv["igt"]

    return Run(
        run_id=run_id,
        world_name=data.get("world_name", ""),
        world_number=parse_world_number(data.get("world_name")),
        end_time=datetime.fromtimestamp(data["date"] / 1000),
        run_type=data.get("run_type", ""),
        completed=bool(data.get("is_completed")),
        final_igt=data.get("final_igt", 0),
        final_rta=data.get("final_rta", 0),
        cheats_from_rta=cheats_from_rta,
        cheats_at_start=cheats and open_lan is None,
        survival=data.get("default_gamemode", 0) == 0 and not data.get("is_hardcore"),
        deaths=_deaths(data),
        splits=splits,
        advancements=advancements,
    )


def _fix_home_portal_blind(splits, data, legit):
    """Leaving the nether through the portal you came in by is still a blind, but
    SpeedRunIGT doesn't record it as one: it records nether_travel_home instead and then
    fills in nether_travel_blind only on reaching the stronghold, at the very same time.
    In that case the blind is when you left the nether."""
    home = next((t["igt"] for t in data.get("timelines", [])
                 if t.get("name") == "nether_travel_home" and legit(t)), None)
    if home is not None and splits.get("blind") is not None and splits.get("blind") == splits.get("stronghold"):
        splits["blind"] = home


def _deaths(data):
    """Death count from the record's vanilla stats ({player uuid: {"stats": {...}}})."""
    return sum(
        player.get("stats", {}).get("minecraft:custom", {}).get("minecraft:deaths", 0)
        for player in data.get("stats", {}).values()
    )


def read_record_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_record(path):
    path = Path(path)
    return parse_record(read_record_json(path), path.stem)
