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

    def item(self, item_id):
        """How to draw an item's icon (see item_model), or None."""
        if not ITEM_ID_RE.match(item_id or ""):
            return None
        key = ("item", item_id)
        with self._lock:
            if key in self._cache:
                return self._cache[key]
            jar = self.jar()
            if not jar:
                return None
            try:
                with zipfile.ZipFile(jar) as z:
                    model = item_model(z, item_id)
            except (OSError, zipfile.BadZipFile):
                return None
            self._cache[key] = model
            return model


ITEM_ID_RE = re.compile(r"^[a-z0-9_]+$")
# Block textures the game colors by biome (as plains); the item icons use the same colors.
TINTS = {"block/spruce_leaves": "#619961", "block/birch_leaves": "#80a755", "block/grass_block_top": "#7cbd6b",
         "block/oak_leaves": "#48b518", "block/jungle_leaves": "#48b518", "block/acacia_leaves": "#48b518",
         "block/dark_oak_leaves": "#48b518", "block/vine": "#48b518", "block/lily_pad": "#208030",
         "block/grass": "#7cbd6b", "block/fern": "#7cbd6b"}


def _texture_name(ref):
    return ref.split(":", 1)[-1]


def item_model(z, item_id):
    """How to draw an item's inventory icon, from its model in the jar:
    {"layers": [texture, ...]} for flat items, {"boxes": [[from, to], ...], "top", "front", "side",
    "tint"} for blocks, {"entity": item id} for the few drawn by code (beds, chests), or None."""
    textures, name, elements, parents = {}, f"item/{item_id}", None, []
    for _ in range(10):  # follow the parents
        try:
            model = json.loads(z.read(f"assets/minecraft/models/{name}.json"))
        except (KeyError, ValueError):
            return None
        for k, v in (model.get("textures") or {}).items():
            textures.setdefault(k, v)
        if elements is None and model.get("elements"):
            elements = model["elements"]
        parent = _texture_name(model.get("parent", ""))
        if not parent:
            break
        parents.append(parent)
        if parent in ("builtin/generated", "builtin/entity"):
            break
        name = parent

    def resolve(key):
        ref = textures.get(key)
        for _ in range(10):
            if not ref or not ref.startswith("#"):
                break
            ref = textures.get(ref[1:])
        return _texture_name(ref) if ref else None

    if "builtin/entity" in parents:
        return {"entity": item_id}
    if "builtin/generated" in parents:
        layers = [resolve(f"layer{i}") for i in range(5)]
        return {"layers": [t for t in layers if t]} if layers[0] else None
    if not elements:
        return None

    def face(*sides):  # the first element's texture on one of these sides
        for e in elements:
            for f in sides:
                ref = ((e.get("faces") or {}).get(f) or {}).get("texture")
                if ref:
                    return resolve(ref[1:]) if ref.startswith("#") else _texture_name(ref)
        return None

    top, front, side = face("up"), face("north", "south"), face("west", "east", "south")
    if not (top and front and side):
        return None
    boxes = [[e["from"], e["to"]] for e in elements if "from" in e and "to" in e]
    return {"boxes": boxes, "top": top, "front": front, "side": side,
            "tint": TINTS.get(top) or TINTS.get(side)}
