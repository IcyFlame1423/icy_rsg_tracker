"""Settings for the app's Settings page: read, validate, save to config.toml, apply live,
and detect Minecraft instances."""

import os
import re
from pathlib import Path

from .config import PRISM_INSTANCES, PROJECT_DIR, Instance, _default_minecraft_dir

RSG_PATTERN = r"^Random Speedrun #\d+$"  # Atum's world names
# Instance names become folder names under data/, so keep them to safe characters.
NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 _.\-]{0,39}$")

LIMITS = {"session_gap_minutes": (1, 24 * 60), "watch_interval_seconds": (1, 60)}


class SettingsError(ValueError):
    def __init__(self, errors):
        super().__init__("; ".join(f"{k}: {v}" for k, v in errors.items()))
        self.errors = errors  # field -> message


def to_json(cfg):
    records = cfg.records_dir
    return {
        "speedrunigt_dir": str(cfg.speedrunigt_dir),
        "records_found": sum(1 for _ in records.glob("*.json")) if records.is_dir() else None,
        "output_dir": str(cfg.output_dir),
        "config_path": str(cfg.path),
        "session_gap_minutes": cfg.session_gap_minutes,
        "include_set_seed": cfg.include_set_seed,
        "watch_interval_seconds": cfg.watch_interval_seconds,
        "instances": [{
            "name": i.name,
            "world_name_pattern": i.world_name_pattern.pattern if i.world_name_pattern else "",
            "minecraft_dir": str(i.minecraft_dir) if i.minecraft_dir else "",
            "logs_found": bool(i.logs_dir and i.logs_dir.is_dir()),
        } for i in cfg.instances],
    }


def _number(data, key, errors):
    lo, hi = LIMITS[key]
    try:
        value = float(data[key])
    except (KeyError, TypeError, ValueError):
        errors[key] = "must be a number"
        return None
    if not lo <= value <= hi:
        errors[key] = f"must be between {lo:g} and {hi:g}"
        return None
    return value


def parse(data):
    """Validate settings sent by the page. Returns a dict of new values or raises
    SettingsError with a message per field."""
    if not isinstance(data, dict):
        raise SettingsError({"settings": "expected an object"})
    errors = {}
    out = {}

    folder = str(data.get("speedrunigt_dir", "")).strip()
    if not folder:
        errors["speedrunigt_dir"] = "is required"
    else:
        out["speedrunigt_dir"] = Path(folder).expanduser()
    out["session_gap_minutes"] = _number(data, "session_gap_minutes", errors)
    out["watch_interval_seconds"] = _number(data, "watch_interval_seconds", errors)
    out["include_set_seed"] = bool(data.get("include_set_seed"))

    instances = []
    raw = data.get("instances")
    if not isinstance(raw, list) or not raw:
        errors["instances"] = "add at least one instance"
        raw = []
    seen = set()
    for i, item in enumerate(raw):
        key = f"instances.{i}"
        if not isinstance(item, dict):
            errors[key] = "expected an object"
            continue
        name = str(item.get("name", "")).strip()
        if not NAME_RE.match(name):
            errors[f"{key}.name"] = "use letters, numbers, spaces, - _ . (up to 40 characters)"
        elif name.lower() in seen:
            errors[f"{key}.name"] = "another instance already has this name"
        seen.add(name.lower())
        pattern_text = str(item.get("world_name_pattern", "")).strip()
        valid = True
        try:
            pattern = re.compile(pattern_text) if pattern_text else None  # empty: every world
        except re.error as e:
            pattern, valid = None, False
            errors[f"{key}.world_name_pattern"] = f"not a valid pattern: {e}"
        mc = str(item.get("minecraft_dir", "")).strip()
        # Empty: the same default loading config.toml uses (a Prism instance with this name),
        # so the running app and the saved file always agree.
        mc_path = Path(mc).expanduser() if mc else _default_minecraft_dir(name)
        if mc_path and not mc_path.is_dir():
            errors[f"{key}.minecraft_dir"] = "folder not found"
        if valid:
            instances.append(Instance(name, pattern, mc_path))
    out["instances"] = instances

    if errors:
        raise SettingsError(errors)
    return out


def apply(cfg, values):
    """Update the running config in place (the tracker and data store share it)."""
    for key, value in values.items():
        setattr(cfg, key, value)


# ---- Writing config.toml (the standard library can read TOML but not write it) ----

def _toml_str(value):
    out = ['"']
    for ch in str(value):
        if ch in '"\\':
            out.append("\\" + ch)
        elif ch == "\n":
            out.append("\\n")
        elif ch == "\t":
            out.append("\\t")
        elif ord(ch) < 0x20 or ord(ch) == 0x7F:
            out.append(f"\\u{ord(ch):04x}")
        else:
            out.append(ch)
    out.append('"')
    return "".join(out)


def _toml_num(value):
    return str(int(value)) if float(value).is_integer() else repr(float(value))


def to_toml(cfg):
    lines = [
        "# Icy RSG Tracker settings. Written by the app's Settings page; you can also edit it by hand.",
        "",
        f"speedrunigt_dir = {_toml_str(cfg.speedrunigt_dir)}",
        f"session_gap_minutes = {_toml_num(cfg.session_gap_minutes)}",
        f"watch_interval_seconds = {_toml_num(cfg.watch_interval_seconds)}",
        f"include_set_seed = {'true' if cfg.include_set_seed else 'false'}",
    ]
    if cfg.output_dir != PROJECT_DIR / "data":
        lines.append(f"output_dir = {_toml_str(cfg.output_dir)}")
    for inst in cfg.instances:
        lines += ["", f"[instances.{_toml_str(inst.name)}]"]
        if inst.world_name_pattern is not None:
            lines.append(f"world_name_pattern = {_toml_str(inst.world_name_pattern.pattern)}")
        if inst.minecraft_dir:
            lines.append(f"minecraft_dir = {_toml_str(inst.minecraft_dir)}")
    return "\n".join(lines) + "\n"


def save(cfg):
    """Write cfg to cfg.path (via a temp file, so a crash never leaves half a file)."""
    tmp = cfg.path.with_suffix(".toml.tmp")
    tmp.write_text(to_toml(cfg), encoding="utf-8")
    tmp.replace(cfg.path)


# ---- Detecting instances ----

def _launcher_dirs():
    """Instance folders of Prism Launcher and MultiMC in their usual places."""
    home = Path.home()
    candidates = [PRISM_INSTANCES]
    for base in (home, home / "Desktop", home / "Downloads", home / "Documents", Path("C:/")):
        candidates += [base / "MultiMC" / "instances", base / "PrismLauncher" / "instances"]
    seen, out = set(), []
    for c in candidates:
        key = os.path.normcase(str(c))
        if key not in seen and c.is_dir():
            seen.add(key)
            out.append(c)
    return out


def detect_instances(extra_dirs=()):
    """Minecraft instances found in launcher folders: name, .minecraft folder, and whether
    it looks like an RSG instance (Atum installed or "Random Speedrun #" worlds)."""
    found = []
    for launcher in [*_launcher_dirs(), *map(Path, extra_dirs)]:
        if not launcher.is_dir():
            continue
        for inst in sorted(launcher.iterdir()):
            mc = next((inst / d for d in ("minecraft", ".minecraft") if (inst / d).is_dir()), None)
            if mc is None:
                continue
            mods = mc / "mods"
            atum = mods.is_dir() and any("atum" in m.name.lower() for m in mods.iterdir())
            saves = mc / "saves"
            rsg_worlds = saves.is_dir() and any(s.name.startswith("Random Speedrun #") for s in saves.iterdir())
            found.append({
                "name": inst.name,
                "minecraft_dir": str(mc),
                "launcher": str(launcher),
                "rsg": bool(atum or rsg_worlds),
                "world_name_pattern": "",  # none: every world (survival, no cheats)
            })
    return found
