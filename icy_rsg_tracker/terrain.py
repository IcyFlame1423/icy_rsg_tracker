"""How open the nether is between two points, read from the world's saved chunks.

For a route (say, the nether portal to the bastion), every chunk the straight line between the
two chunks' centres crosses is read, and its blocks from y 30 to 90 are counted: the share that
is open (air, lava, and anything with nothing to dig through) is the route's openness. More open
terrain is faster to cross; walls have to be dug through.

Optionally (bucket 3, before fire resistance) a lava ocean counts as closed: a column with lava
at the ocean's surface (y 31; the nether's sea level is 32) and nothing solid above it up to
y 90 has to be bridged, so all its blocks in the band count as closed.

Reads Minecraft 1.16's Anvil region files (saves/<world>/DIM-1/region/r.X.Z.mca) with the
standard library only. The saved world already has the player's own tunnels and bridges in it,
but a tunnel is a tiny part of a chunk's 16 x 16 x 61 blocks.
"""

import gzip
import math
import struct
import zlib
from pathlib import Path

Y_LOW, Y_HIGH = 30, 90                   # the band counted (inclusive)
AIR = {"minecraft:air", "minecraft:cave_air", "minecraft:void_air", "minecraft:fire", "minecraft:soul_fire",
       "minecraft:crimson_roots", "minecraft:warped_roots", "minecraft:nether_sprouts",
       "minecraft:weeping_vines", "minecraft:weeping_vines_plant", "minecraft:twisting_vines",
       "minecraft:twisting_vines_plant", "minecraft:crimson_fungus", "minecraft:warped_fungus",
       "minecraft:brown_mushroom", "minecraft:red_mushroom"}  # nothing to dig through
LAVA = {"minecraft:lava"}
OCEAN_Y = 31                             # the lava ocean's surface (sea level 32)


# ---- NBT (just enough to read a chunk) ----

def _read_nbt(data, pos, tag):
    if tag == 1:
        return data[pos], pos + 1
    if tag == 2:
        return struct.unpack_from(">h", data, pos)[0], pos + 2
    if tag == 3:
        return struct.unpack_from(">i", data, pos)[0], pos + 4
    if tag == 4:
        return struct.unpack_from(">q", data, pos)[0], pos + 8
    if tag == 5:
        return struct.unpack_from(">f", data, pos)[0], pos + 4
    if tag == 6:
        return struct.unpack_from(">d", data, pos)[0], pos + 8
    if tag == 7:
        n = struct.unpack_from(">i", data, pos)[0]
        return data[pos + 4:pos + 4 + n], pos + 4 + n
    if tag == 8:
        n = struct.unpack_from(">H", data, pos)[0]
        return data[pos + 2:pos + 2 + n].decode("utf-8", "replace"), pos + 2 + n
    if tag == 9:
        item, n = data[pos], struct.unpack_from(">i", data, pos + 1)[0]
        pos += 5
        out = []
        for _ in range(n):
            value, pos = _read_nbt(data, pos, item)
            out.append(value)
        return out, pos
    if tag == 10:
        out = {}
        while True:
            item = data[pos]
            pos += 1
            if item == 0:
                return out, pos
            n = struct.unpack_from(">H", data, pos)[0]
            name = data[pos + 2:pos + 2 + n].decode("utf-8", "replace")
            out[name], pos = _read_nbt(data, pos + 2 + n, item)
    if tag == 11:
        n = struct.unpack_from(">i", data, pos)[0]
        return list(struct.unpack_from(f">{n}i", data, pos + 4)), pos + 4 + 4 * n
    if tag == 12:
        n = struct.unpack_from(">i", data, pos)[0]
        return list(struct.unpack_from(f">{n}q", data, pos + 4)), pos + 4 + 8 * n
    raise ValueError(f"unknown NBT tag {tag}")


def _chunk(region_dir, cx, cz, cache):
    """A chunk's NBT ("Level" compound), or None if it isn't saved."""
    key = (cx >> 5, cz >> 5)
    if key not in cache:
        try:
            cache[key] = (Path(region_dir) / f"r.{key[0]}.{key[1]}.mca").read_bytes()
        except OSError:
            cache[key] = None
    data = cache[key]
    if not data:
        return None
    i = 4 * ((cx & 31) + (cz & 31) * 32)
    offset = int.from_bytes(data[i:i + 3], "big") * 4096
    if not offset or offset + 5 > len(data):
        return None
    length, compression = int.from_bytes(data[offset:offset + 4], "big"), data[offset + 4]
    raw = data[offset + 5:offset + 4 + length]
    try:
        raw = zlib.decompress(raw) if compression == 2 else gzip.decompress(raw) if compression == 1 else None
    except (zlib.error, OSError):
        return None
    if raw is None or raw[0] != 10:
        return None
    root, _ = _read_nbt(raw, 3 + struct.unpack_from(">H", raw, 1)[0], 10)
    return root.get("Level")


SOLID, OPEN, LIQUID = 0, 1, 2


def _kinds(level, y_low, y_high):
    """{y: [kind of each of the layer's 256 blocks, index z * 16 + x]} for y_low..y_high."""
    sections = {s.get("Y"): s for s in level.get("Sections") or [] if isinstance(s, dict)}
    layers = {}
    for sy in range(y_low // 16, y_high // 16 + 1):
        lo, hi = max(y_low, sy * 16), min(y_high, sy * 16 + 15)
        section = sections.get(sy)
        palette, states = (section or {}).get("Palette"), (section or {}).get("BlockStates")
        if not palette or not states:  # a section that isn't saved is all air
            for y in range(lo, hi + 1):
                layers[y] = [OPEN] * 256
            continue
        kinds = [OPEN if p.get("Name") in AIR else LIQUID if p.get("Name") in LAVA else SOLID for p in palette]
        bits = max(4, (len(palette) - 1).bit_length())
        per_long, mask = 64 // bits, (1 << bits) - 1
        for y in range(lo, hi + 1):
            base = (y - sy * 16) * 256
            layer = []
            for index in range(base, base + 256):
                value = ((states[index // per_long] & 0xFFFFFFFFFFFFFFFF) >> ((index % per_long) * bits)) & mask
                layer.append(kinds[value] if value < len(kinds) else SOLID)
            layers[y] = layer
    return layers


def chunk_counts(level, ocean_closed=False):
    """(open blocks, all blocks) from y Y_LOW to Y_HIGH in a chunk: air and lava are open, but
    with ocean_closed, every block in a lava ocean column is closed."""
    layers = _kinds(level, min(Y_LOW, OCEAN_Y), Y_HIGH)
    band = range(Y_LOW, Y_HIGH + 1)
    open_blocks = 0
    for column in range(256):
        if ocean_closed and layers[OCEAN_Y][column] == LIQUID and all(
                layers[y][column] != SOLID for y in range(OCEAN_Y + 1, Y_HIGH + 1)):
            continue  # open lava ocean: has to be bridged
        open_blocks += sum(1 for y in band if layers[y][column] != SOLID)
    return open_blocks, 256 * len(band)


def route_chunks(a, b):
    """The chunks the line between the centres of a's and b's chunks crosses, in order."""
    ax, az = (math.floor(a["x"]) >> 4) * 16 + 8, (math.floor(a["z"]) >> 4) * 16 + 8
    bx, bz = (math.floor(b["x"]) >> 4) * 16 + 8, (math.floor(b["z"]) >> 4) * 16 + 8
    steps = max(1, int(math.hypot(bx - ax, bz - az)))
    seen = []
    for k in range(steps + 1):
        x, z = ax + (bx - ax) * k / steps, az + (bz - az) * k / steps
        c = (math.floor(x) >> 4, math.floor(z) >> 4)
        if not seen or seen[-1] != c:
            seen.append(c)
    return seen


def openness(region_dir, a, b, ocean_closed=False):
    """Percent of open blocks (y 30-90) in the chunks between points a and b ({x, z}, nether
    coordinates), or None if none of them is saved. ocean_closed: lava oceans count as closed."""
    if not a or not b:
        return None
    cache, open_blocks, total = {}, 0, 0
    for cx, cz in route_chunks(a, b):
        level = _chunk(region_dir, cx, cz, cache)
        if level is None:
            continue
        o, t = chunk_counts(level, ocean_closed)
        open_blocks += o
        total += t
    return round(100 * open_blocks / total, 1) if total else None
