"""Settings, read from config.toml in the project folder if it exists."""

import os
import re
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

# Where config.toml and data/ live: the project folder, or the .exe's folder when packaged.
PROJECT_DIR = (Path(sys.executable).resolve().parent if getattr(sys, "frozen", False)
               else Path(__file__).resolve().parent.parent)
DEFAULT_CONFIG_PATH = PROJECT_DIR / "config.toml"


PRISM_INSTANCES = Path(os.environ.get("APPDATA", Path.home())) / "PrismLauncher" / "instances"


@dataclass
class Instance:
    """A Minecraft instance. Every instance writes to the same SpeedRunIGT records
    folder, so records are matched to an instance by world name."""
    name: str
    world_name_pattern: re.Pattern
    # The instance's .minecraft folder; its logs/ are used to classify deaths.
    # None -> death respawn columns are left blank.
    minecraft_dir: Path | None = None

    def owns(self, world_name):
        return bool(self.world_name_pattern.search(world_name))

    @property
    def logs_dir(self):
        return self.minecraft_dir / "logs" if self.minecraft_dir else None


def _default_minecraft_dir(name):
    path = PRISM_INSTANCES / name / "minecraft"
    return path if path.is_dir() else None


def default_instances():
    # Atum names RSG worlds "Random Speedrun #N".
    return [Instance("speedrun", re.compile(r"^Random Speedrun #\d+$"),
                     _default_minecraft_dir("speedrun"))]


@dataclass
class Config:
    speedrunigt_dir: Path = Path.home() / "speedrunigt"
    output_dir: Path = PROJECT_DIR / "data"
    session_gap_minutes: float = 30
    include_set_seed: bool = False
    watch_interval_seconds: float = 3
    instances: list = field(default_factory=default_instances)
    path: Path = DEFAULT_CONFIG_PATH  # where these settings are read from / saved to

    @property
    def records_dir(self):
        return self.speedrunigt_dir / "records"

    def instance_dir(self, instance):
        return self.output_dir / instance.name

    def runs_csv(self, instance):
        return self.instance_dir(instance) / "runs.csv"

    def instance_for(self, world_name):
        """The first instance whose pattern matches, or None."""
        for instance in self.instances:
            if instance.owns(world_name):
                return instance
        return None


def _detected_instance():
    """On a first start with no "speedrun" Prism instance: the RSG instance found in the
    usual launcher folders (the one played most recently), or None."""
    from .settings import detect_instances  # settings imports this module
    rsg = [d for d in detect_instances() if d["rsg"]]
    if not rsg:
        return None
    saves = lambda d: (Path(d["minecraft_dir"]) / "saves").stat().st_mtime if (Path(d["minecraft_dir"]) / "saves").is_dir() else 0
    best = max(rsg, key=saves)
    name = re.sub(r"[^A-Za-z0-9 _.\-]", "", best["name"]).strip()[:40] or "speedrun"
    return Instance(name, re.compile(best["world_name_pattern"]), Path(best["minecraft_dir"]))


def load_config(path=DEFAULT_CONFIG_PATH):
    path = Path(path)
    cfg = Config(path=path)
    if not path.exists():
        if cfg.instances[0].minecraft_dir is None and (found := _detected_instance()):
            cfg.instances = [found]
        return cfg
    with open(path, "rb") as f:
        data = tomllib.load(f)
    if "speedrunigt_dir" in data:
        cfg.speedrunigt_dir = Path(data["speedrunigt_dir"]).expanduser()
    if "output_dir" in data:
        out = Path(data["output_dir"]).expanduser()
        cfg.output_dir = out if out.is_absolute() else PROJECT_DIR / out
    if "session_gap_minutes" in data:
        cfg.session_gap_minutes = float(data["session_gap_minutes"])
    if "include_set_seed" in data:
        cfg.include_set_seed = bool(data["include_set_seed"])
    if "watch_interval_seconds" in data:
        cfg.watch_interval_seconds = float(data["watch_interval_seconds"])
    if "instances" in data:
        cfg.instances = [
            Instance(
                name,
                re.compile(settings["world_name_pattern"]),
                Path(settings["minecraft_dir"]).expanduser() if "minecraft_dir" in settings
                else _default_minecraft_dir(name),
            )
            for name, settings in data["instances"].items()
        ]
    return cfg
