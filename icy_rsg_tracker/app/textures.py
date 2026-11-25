"""Block and item textures for the app's icons, read from the player's own Minecraft jar.

Nothing of Mojang's is shipped with this project: the textures are read on demand from
the client jar that the launcher already downloaded (Prism/MultiMC keep it under
libraries/, the official launcher under versions/).
"""

import json
import os
import re
import threading
import zipfile
from pathlib import Path

NAME_RE = re.compile(r"^(item|block|entity|font|mob_effect)(/[a-z0-9_]+)+$")
WANTED_VERSION = "1.16.1"
MAX_TEXTURE_BYTES = 100_000


def _instance_version(minecraft_dir):
    """The Minecraft version of a Prism/MultiMC instance (from mmc-pack.json), or None."""
    try:
        pack = json.loads((minecraft_dir.parent / "mmc-pack.json").read_text(encoding="utf-8"))
        return next(c["version"] for c in pack["components"] if c.get("uid") == "net.minecraft")
    except (OSError, ValueError, KeyError, StopIteration, TypeError):
        return None


def find_client_jar(instances):
    """The first Minecraft client jar found: the instances' own version first, then 1.16.1."""
    candidates = []
    for inst in instances:
        if not inst.minecraft_dir:
            continue
        version = _instance_version(inst.minecraft_dir) or WANTED_VERSION
        # <launcher>/instances/<name>/minecraft -> <launcher>/libraries/...
        launcher = inst.minecraft_dir.parent.parent.parent
        candidates.append(launcher / "libraries" / "com" / "mojang" / "minecraft" / version
                          / f"minecraft-{version}-client.jar")
    appdata = Path(os.environ.get("APPDATA", Path.home()))
    for launcher in ("PrismLauncher", "MultiMC"):
        candidates.append(appdata / launcher / "libraries" / "com" / "mojang" / "minecraft"
                          / WANTED_VERSION / f"minecraft-{WANTED_VERSION}-client.jar")
    candidates.append(appdata / ".minecraft" / "versions" / WANTED_VERSION / f"{WANTED_VERSION}.jar")
    return next((p for p in candidates if p.is_file()), None)


class Textures:
    """Reads textures out of the client jar, remembering the ones already read."""

    def __init__(self, get_cfg):
        self._get_cfg = get_cfg  # settings can change while the app runs
        self._cache = {}
        self._lock = threading.Lock()

    def jar(self):
        return find_client_jar(self._get_cfg().instances)

    def get(self, name):
        """PNG bytes of e.g. "item/ender_eye", or None (bad name, no jar, no such texture)."""
        if not NAME_RE.match(name or ""):
            return None
        with self._lock:
            if name in self._cache:
                return self._cache[name]
            png = None
            jar = self.jar()
            if jar:
                try:
                    with zipfile.ZipFile(jar) as z:
                        info = z.getinfo(f"assets/minecraft/textures/{name}.png")
                        if info.file_size <= MAX_TEXTURE_BYTES:
                            png = z.read(info)
                except (OSError, KeyError, zipfile.BadZipFile):
                    png = None
            if png is not None:  # don't remember misses: the jar may turn up later
                self._cache[name] = png
            return png
