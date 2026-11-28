"""Reading the Hermes mod's play log (saves/<world>/hermes/play.log).

Hermes writes play.log, one JSON object per line, when the world is closed. While the world
is open, Hermes only keeps a ciphered copy in hermes/restricted/; that copy must not be used
during a run, and this module never touches it.

What the tracker takes from it:
- the seed, from a "seed" event (Hermes writes one when /seed is typed in the world);
- how many of each key item the run obtained, from the inventory events (see ItemCounter);
- what happened in each part of the run, with the ghost's positions (see phases.py).
"""

import json
from collections import defaultdict

from . import phases, terrain

# The items counted, by what they're called in runs.csv.
# These count as the most held at once rather than every one obtained.
# Bump whenever what's worked out from a play log changes (this file, phases.py, terrain.py), so
# runs already in runs.csv are read again instead of keeping their stored results (see play_log_key).
PLAY_LOG_VERSION = 7

MOST_HELD = ("ender_pearls", "obsidian")
ITEMS = ("ender_pearls", "blaze_rods", "beds", "respawn_anchors", "fire_resistance", "obsidian")
# More about each, also kept in runs.csv (see ItemCounter.details).
DETAILS = (
    "blazes_killed",
    "pearls_used",            # thrown before entering the End
    "pearls_into_eyes",       # crafted into eyes of ender
    "beds_nether",            # blown up in the nether, outside a fortress
    "beds_fortress",          # blown up in a fortress
    "beds_end",               # blown up in the End (to kill the dragon)
    "beds_lost",              # placed in the overworld and never broken, or dropped and never picked up
    "anchors_end",            # placed in the End
    "anchors_lost",           # placed outside the End and never broken (or blown up), or dropped and lost
    "fire_resistance_used",   # drunk or thrown
    "obsidian_bastion",       # obtained inside a bastion
    "diamond_pickaxe",        # "1" if the run had a diamond pickaxe, "0" if not
)

# Dropped items despawn after 5 minutes: after that, a dropped item can't be picked up again.
# Measured in in-game time, which (like an item's age) stops while the world is paused or closed:
# leaving the world and coming back later doesn't make the items despawn.
DESPAWN_MS = 5 * 60 * 1000
# Events from the same moment (a death and the inventory emptying, a drop and the slot
# changing) are a few milliseconds apart in the log; this is how far apart they may be.
SAME_MOMENT_MS = 1500
# How recently a block must have been mined for picking one up to count as getting it back
# (a bed placed for a death reset, then broken and picked up).
MINED_RECENTLY_MS = 30_000
# Screens whose items stay in the world: items put in them can be taken out again.
STORAGE_SCREENS = {"container.chest", "container.chestDouble", "container.barrel", "container.shulkerBox",
                   "container.enderchest", "container.hopper", "container.dispenser", "container.dropper"}


def item_kind(item):
    """Which counted item an inventory stack is (see ITEMS), or None."""
    if not item:
        return None
    item_id = item.get("id", "")
    if item_id == "minecraft:ender_pearl":
        return "ender_pearls"
    if item_id == "minecraft:blaze_rod":
        return "blaze_rods"
    if item_id.endswith("_bed"):
        return "beds"
    if item_id == "minecraft:respawn_anchor":
        return "respawn_anchors"
    if item_id == "minecraft:obsidian":
        return "obsidian"
    if item_id in ("minecraft:potion", "minecraft:splash_potion", "minecraft:lingering_potion"):
        potion = (item.get("tag") or {}).get("Potion", "")
        return "fire_resistance" if potion.endswith("fire_resistance") else None
    return None


def stat_kind(stat):
    """The counted item a stat is about ("minecraft.used:minecraft.white_bed" -> "beds"), or None.
    Potion stats don't say which potion, so they count for fire resistance."""
    item = stat.split(":", 1)[-1]
    if item in ("minecraft.potion", "minecraft.splash_potion", "minecraft.lingering_potion"):
        return "fire_resistance"
    return item_kind({"id": item.replace("minecraft.", "minecraft:", 1)})


class ItemCounter:
    """How many of each item a run obtained, from the inventory as it changed.

    Every time the inventory gains an item, it's either new or one coming back:
    - dropped on death or thrown out, then picked up again (within DESPAWN_MS);
    - put in a chest (or similar), then taken out again;
    - moved around in a menu (picked up with the cursor, then put down);
    - placed (a bed, an anchor, obsidian), then broken and picked up again.
    Only new ones count. Blaze rods only count when picked up (from blazes), not from chests.
    Ender pearls and obsidian are the most the inventory held at once (they're gathered, then used).
    Items crafted (beds, anchors) count as new when they land in the inventory.
    Counting stops once the world is opened to LAN (cheats could give anything after that).

    It also notes where things went (see details()): where each bed and anchor was placed,
    and whether it was broken again afterwards; pearls thrown and crafted into eyes; potions
    used; blazes killed; and whether obsidian came from inside a bastion.
    """

    def __init__(self):
        self.slots = {}                  # slot -> (kind, count)
        self.obtained = dict.fromkeys(ITEMS, 0)
        self.dropped = defaultdict(list)  # kind -> [[count, in-game time it despawns]]
        self.stored = defaultdict(int)    # kind -> count in containers or on the cursor
        self.placed = defaultdict(int)    # kind -> count placed that could be broken and picked up
        self.screen = None                # the open screen's title key, or None
        self.screen_open = False
        self.screen_closed_at = None      # when the last screen closed (ms)
        self.lan = False                  # opened to LAN: nothing after that counts
        self.dimension = "minecraft:overworld"
        self.death_at = None              # when the player last died (ms)
        self.recent = []                  # recent stats: (time, stat, diff)
        self.igt = 0                      # in-game time of the latest event (ms)
        self.structures = set()           # the structures the player is inside
        self.unbroken = defaultdict(int)  # beds/anchors placed and not (yet) broken again
        self.placed_at = defaultdict(list)  # kind -> [(dimension, where it was counted)], as placed
        self.counts = defaultdict(int)    # the details() numbers being added up
        self.diamond_pickaxe = False

    def _recent_stat(self, now, prefix, kind, within=SAME_MOMENT_MS):
        """Take the amount of a matching stat change near `now` (each is only used once)."""
        for event in self.recent:
            time, stat, diff = event
            if diff > 0 and stat.startswith(prefix) and abs(now - time) <= within and stat_kind(stat) == kind:
                event[2] = 0
                return diff
        return 0

    def event(self, event):
        kind, data, now = event.get("type"), event.get("data") or {}, event.get("time") or 0
        if kind == "game_info" and data.get("open_to_lan"):
            self.lan = True
        if self.lan:
            return
        igt = (event.get("speedrunigt") or {}).get("igt")
        if igt:  # 0 when the timer isn't running (e.g. as the world closes)
            self.igt = igt
        if kind == "screen":
            title = data.get("title") or {}
            self.screen = title.get("translate") if isinstance(title, dict) else None
            was_open = self.screen_open
            self.screen_open = bool(data) and data.get("title") is not None and not data.get("is_pause")
            if was_open and not self.screen_open:
                self.screen_closed_at = now
        elif kind == "dimension":
            self.dimension = data.get("dimension") or self.dimension
        elif kind == "inside_structures":
            self.structures = {s.split(":")[-1] for s in data.get("structures") or []}
        elif kind == "stat":
            stat, diff = data.get("stat", ""), data.get("diff") or 0
            if stat == "minecraft.custom:minecraft.deaths":
                self.death_at = now
            elif stat.startswith(("minecraft.dropped:", "minecraft.used:", "minecraft.mined:")):
                self.recent = [e for e in self.recent if now - e[0] <= MINED_RECENTLY_MS]
                self.recent.append([now, stat, diff])
            if diff > 0:
                self._note(stat, diff)
        elif kind == "inventory_slots":
            self._slots(data.get("slots") or {}, now)

    def _note(self, stat, n):
        """Add a stat change to the details."""
        kind, item = stat_kind(stat), stat.split(":", 1)[-1]
        if stat == "minecraft.killed:minecraft.blaze":
            self.counts["blazes_killed"] += n
        elif stat == "minecraft.crafted:minecraft.ender_eye":
            self.counts["pearls_into_eyes"] += n  # one pearl per eye
        elif stat.startswith("minecraft.used:") and kind == "ender_pearls":
            if self.dimension != "minecraft:the_end":
                self.counts["pearls_used"] += n
        elif stat.startswith("minecraft.used:") and kind in ("beds", "respawn_anchors"):
            if self.dimension == "minecraft:the_end":
                where = "beds_end" if kind == "beds" else "anchors_end"
            elif kind == "beds" and self.dimension == "minecraft:the_nether":
                where = "beds_fortress" if "fortress" in self.structures else "beds_nether"
            else:  # a bed in the overworld, an anchor in the overworld or the nether
                where = None  # unbroken until it's broken again
            for _ in range(n):
                self.placed_at[kind].append((self.dimension, where))
                self._where(kind, where, 1)
        elif stat.startswith("minecraft.mined:") and kind in ("beds", "respawn_anchors"):
            # Broken again: the latest one placed in this dimension. It wasn't blown up after
            # all (a bed placed in the End or the nether, then broken instead). One not placed
            # by the player, e.g. a village bed, has nothing to match.
            for _ in range(n):
                placed = self.placed_at[kind]
                i = next((i for i in range(len(placed) - 1, -1, -1) if placed[i][0] == self.dimension), None)
                if i is not None:
                    self._where(kind, placed.pop(i)[1], -1)
        elif item == "minecraft.diamond_pickaxe" and stat.startswith(("minecraft.crafted:", "minecraft.picked_up:")):
            self.diamond_pickaxe = True

    def _where(self, kind, where, n):
        if where:
            self.counts[where] = max(0, self.counts[where] + n)
        else:
            self.unbroken[kind] = max(0, self.unbroken[kind] + n)

    def details(self):
        """{name in DETAILS: number}, for what the run did with its items."""
        def never_picked_up(k):  # dropped (on death or thrown) and not picked up again
            return sum(n for n, _ in self.dropped[k])
        out = {name: self.counts[name] for name in DETAILS}
        out["beds_lost"] = self.unbroken["beds"] + never_picked_up("beds")
        out["anchors_lost"] = self.unbroken["respawn_anchors"] + never_picked_up("respawn_anchors")
        out["diamond_pickaxe"] = int(self.diamond_pickaxe)
        out["obsidian_bastion"] = min(out["obsidian_bastion"], self.obtained["obsidian"])
        return out

    def _slots(self, changes, now):
        if any(item and item.get("id") == "minecraft:diamond_pickaxe" for item in changes.values()):
            self.diamond_pickaxe = True
        before = self._totals()
        for slot, item in changes.items():
            k = item_kind(item)
            if k:
                self.slots[slot] = (k, item.get("Count", 1))
            else:
                self.slots.pop(slot, None)
        after = self._totals()
        for k in MOST_HELD:
            self.obtained[k] = max(self.obtained[k], after.get(k, 0))
        for k in ITEMS:
            change = after.get(k, 0) - before.get(k, 0)
            if change < 0:
                self._lost(k, -change, now)
            elif change > 0:
                self._gained(k, change, now)

    def _totals(self):
        totals = defaultdict(int)
        for k, n in self.slots.values():
            totals[k] += n
        return totals

    def _lost(self, k, n, now):
        if self.death_at is not None and abs(now - self.death_at) <= SAME_MOMENT_MS:
            self.dropped[k].append([n, self.igt + DESPAWN_MS])  # dropped on death
            return
        thrown = min(n, self._recent_stat(now, "minecraft.dropped:", k))
        if thrown:
            self.dropped[k].append([thrown, self.igt + DESPAWN_MS])
            n -= thrown
        if n and self.screen_open:
            self.stored[k] += n  # into a container, onto the cursor, or into the crafting grid
            return
        placed = min(n, self._recent_stat(now, "minecraft.used:", k))
        if k == "fire_resistance":
            self.counts["fire_resistance_used"] += placed  # drunk or thrown
        # Anything placed can be broken and picked up again, even a bed in the nether or the
        # End (one that blows up is never broken, so nothing picked up is matched to it).
        if placed and k in ("beds", "respawn_anchors", "obsidian"):
            self.placed[k] += placed
        # Anything else is used up: thrown (pearls), drunk, crafted into something, burnt.

    def _gained(self, k, n, now):
        # Taken back out of a container or off the cursor, or out of the crafting grid as the
        # screen closes (the inventory changes just after the screen closes).
        closing = self.screen_closed_at is not None and now - self.screen_closed_at <= SAME_MOMENT_MS
        if (self.screen_open or closing) and self.stored[k]:
            back = min(n, self.stored[k])
            self.stored[k] -= back
            n -= back
        for drop in self.dropped[k]:  # dropped items picked up again
            if n and drop[0] and self.igt <= drop[1]:
                back = min(n, drop[0])
                drop[0] -= back
                n -= back
        if n and self.placed[k] and self._recent_stat(now, "minecraft.mined:", k, MINED_RECENTLY_MS):
            back = min(n, self.placed[k])  # placed, then broken and picked up again
            self.placed[k] -= back
            n -= back
        if n and k == "blaze_rods" and self.screen in STORAGE_SCREENS:
            return  # from a chest, not from a blaze
        if k == "obsidian" and "bastion_remnant" in self.structures:
            self.counts["obsidian_bastion"] += n
        if k not in MOST_HELD:  # those are counted in _slots
            self.obtained[k] += n


def installed(minecraft_dir):
    """Whether the instance has the Hermes mod (a hermes*.jar in its mods folder): the tracker
    needs it for item counts, the run breakdown, seed types and scores."""
    try:
        return any(p.name.lower().startswith("hermes") and p.name.lower().endswith(".jar")
                   for p in (minecraft_dir / "mods").iterdir())
    except OSError:
        return False


def play_log_path(minecraft_dir, world_name):
    if not minecraft_dir or not world_name:
        return None
    return minecraft_dir / "saves" / world_name / "hermes" / "play.log"


def play_log_key(minecraft_dir, world_name):
    """A fingerprint of the world's play log: PLAY_LOG_VERSION, its size and when it changed, or
    None without one. Only the folder entry is read, not the file (opening thousands of play
    logs is what makes a rebuild slow), so unchanged runs can keep what was worked out before."""
    path = play_log_path(minecraft_dir, world_name)
    try:
        st = path.stat() if path else None
    except OSError:
        return None
    return f"{PLAY_LOG_VERSION}:{st.st_size}:{st.st_mtime_ns}" if st else None


def read_play_log(minecraft_dir, world_name):
    """What the tracker uses from a world's play log, or None if there isn't one (Hermes isn't
    installed, the world is still open, or it was deleted):
    {"seed": text or None (only if /seed was typed), "items": {item: count obtained},
     "details": ItemCounter.details(), "phases": phases.PhaseTracker.summary()}."""
    path = play_log_path(minecraft_dir, world_name)
    if path is None:
        return None
    seed, counter, tracker, first_time = None, ItemCounter(), phases.PhaseTracker(), None
    try:
        with open(path, encoding="utf-8", errors="replace") as f:
            for line in f:
                try:
                    event = json.loads(line)
                except ValueError:
                    continue  # a line cut short
                if not isinstance(event, dict):
                    continue
                if event.get("type") == "seed":
                    value = (event.get("data") or {}).get("seed")
                    if isinstance(value, int):
                        seed = str(value)
                first_time = first_time or event.get("time")
                counter.event(event)
                tracker.event(event)
    except OSError:
        return None
    ghost = phases.Ghost.read(path.parent, first_time)
    if ghost:  # buried treasures, which Hermes doesn't report (see PhaseTracker.add_buried_treasures)
        overworld = path.parent.parent / "region"

        def is_treasure(time):
            at = ghost.position(time)
            return bool(at) and terrain.has_structure(overworld, at["x"], at["z"], "buried_treasure")
        tracker.add_buried_treasures(is_treasure)
    summary = tracker.summary(ghost)
    if ghost:  # the terrain along each nether route, from the world's saved chunks
        region = path.parent.parent / "DIM-1" / "region"
        for bucket, (start, end, ocean_closed) in tracker.terrain_routes(ghost.position).items():
            summary["columns"][f"terrain_{bucket}"] = terrain.openness(region, start, end, ocean_closed)
    return {"seed": seed, "items": counter.obtained, "details": counter.details(), "phases": summary}


def read_seed(minecraft_dir, world_name):
    """The world's seed as text if /seed was typed in it, else None."""
    log = read_play_log(minecraft_dir, world_name)
    return log["seed"] if log else None
