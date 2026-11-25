"""The player shown in the top bar: their username and skin (for the head).

The username and UUID come from the instance's usercache.json, which Minecraft writes
when you join a world. The skin comes from Mojang's own servers (the session server
gives the skin's address on textures.minecraft.net) and is cached in the instance's data
folder, so it still shows when offline.
"""

import base64
import json
import re
import time
from urllib.request import urlopen

UUID_RE = re.compile(r"^[0-9a-fA-F]{8}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{4}-?[0-9a-fA-F]{12}$")
PROFILE_URL = "https://sessionserver.mojang.com/session/minecraft/profile/{}"
SKIN_HOST = re.compile(r"^https?://textures\.minecraft\.net/texture/[0-9a-f]+$")
REFRESH_SECONDS = 24 * 3600  # look for a new skin once a day
RETRY_SECONDS = 600          # after a failed download, wait before trying again
TIMEOUT = 5
MAX_SKIN_BYTES = 200_000

_failed = {}  # uuid -> time of the last failed download


def player(inst):
    """{"name", "uuid"} of the instance's player, or None if unknown.

    usercache.json lists everyone the instance has seen; the player is the entry used
    most recently (the latest expiry, as each use pushes it a month ahead).
    """
    if not inst.minecraft_dir:
        return None
    try:
        entries = json.loads((inst.minecraft_dir / "usercache.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    valid = [e for e in entries if isinstance(e, dict) and isinstance(e.get("name"), str)
             and UUID_RE.match(str(e.get("uuid", "")))]
    if not valid:
        return None
    latest = max(valid, key=lambda e: str(e.get("expiresOn", "")))
    return {"name": latest["name"], "uuid": latest["uuid"]}


def _download_skin(uuid):
    with urlopen(PROFILE_URL.format(uuid.replace("-", "")), timeout=TIMEOUT) as res:
        profile = json.load(res)
    textures = next(p["value"] for p in profile.get("properties", []) if p.get("name") == "textures")
    url = json.loads(base64.b64decode(textures))["textures"]["SKIN"]["url"]
    if not SKIN_HOST.match(url):
        raise ValueError(f"unexpected skin address {url}")
    with urlopen(url.replace("http://", "https://", 1), timeout=TIMEOUT) as res:
        png = res.read(MAX_SKIN_BYTES + 1)
    if len(png) > MAX_SKIN_BYTES or not png.startswith(b"\x89PNG"):
        raise ValueError("not a skin image")
    return png


def skin(inst, cache_dir, download=_download_skin):
    """The player's skin as PNG bytes, or None (no player, or offline with no cached skin)."""
    who = player(inst)
    if not who:
        return None
    png_path = cache_dir / "skin.png"
    meta_path = cache_dir / "skin.json"
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        meta = {}
    cached = png_path.read_bytes() if png_path.is_file() and meta.get("uuid") == who["uuid"] else None
    fresh = cached and time.time() - meta.get("fetched", 0) < REFRESH_SECONDS
    if fresh or time.time() - _failed.get(who["uuid"], 0) < RETRY_SECONDS:
        return cached
    try:
        png = download(who["uuid"])
    except Exception:  # offline, Mojang down, odd profile: keep what we have
        _failed[who["uuid"]] = time.time()
        return cached
    cache_dir.mkdir(parents=True, exist_ok=True)
    png_path.write_bytes(png)
    meta_path.write_text(json.dumps({"uuid": who["uuid"], "fetched": time.time()}), encoding="utf-8")
    return png
