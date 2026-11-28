"""What happened in each part of a run (overworld, nether, stronghold, End), from the Hermes
play log and ghost (see hermes.py for the files).

The play log gives inventory changes, stats, the structures the player is in (checked about
once a second), and positions when changing dimension. The ghost gives the player's position
every tick, for where the player was when entering or leaving a structure. Distances are
straight lines across the ground (x and z, not y) between two such points.
"""

import bisect
import math
import struct
from collections import defaultdict

# The ghost file: one record per tick. Hermes 0.16 writes 46 bytes: time (ms since 1970),
# x, y, z, yaw, pitch, health, hotbar slot, flags. (Older versions wrote 42, without health.)
GHOST_RECORD = struct.Struct(">qdddfffbb")
# A gap in the ghost longer than this (the world closed, or the buffer was full) isn't walked.
GHOST_GAP_MS = 1000

# A chest opened this long before Hermes notices the structure still counts as in it.
STRUCTURE_LAG_MS = 3000
# Leaving a structure and entering the same kind again within this long is one visit.
SAME_VISIT_MS = 60_000
# Structures that don't count as the last one before the nether (or on the way to it).
NOT_LAST_STRUCTURE = {"ocean_ruin"}
# Stepping out of a bastion for less than this (along its edge, say) is still being in it.
BASTION_GAP_MS = 30_000
# The performance model's buckets with a time of their own (bucket 10, the End, is the rest of the
# run, from the record's final time).
BUCKETS = tuple(f"bucket_{i}" for i in range(1, 10))
# A dragon killed this soon after the first bed or anchor blows up in the End died on that perch
# (a dragon that survives flies off, and the next perch takes about a minute or more).
ONE_CYCLE_MS = 30_000
# A dimension change this soon after dying is a respawn, not a trip through a portal.
RESPAWN_MS = 2000
SEED_TYPES = {"village", "shipwreck", "desert_pyramid", "ruined_portal", "buried_treasure"}
PICKAXES = ("minecraft:iron_pickaxe", "minecraft:diamond_pickaxe", "minecraft:netherite_pickaxe")
# What runs.csv keeps as columns of their own: distances in blocks, times in ms.
COLUMNS = (
    "spawn_to_structures",   # world spawn to each overworld structure entered in turn, to the last
    "to_first_structure",    # nether enter to the first bastion or fortress
    "bastion_time",          # in a bastion
    "first_to_last_rod",     # first blaze rod to the last (before leaving the nether)
    # For the performance model (model.py):
    "last_structure",        # the seed type: the last looted village, shipwreck, desert temple or
                             # buried treasure, else a looted ruined portal ("" if none: structureless;
                             # before the nether, only set once one was looted)
    "spawn_to_structure",    # world spawn to entering the seed-type structure (last_structure)
    "structure_to_portal",   # leaving the seed-type structure to the overworld nether portal
    "bastion_to_fortress",   # leaving the bastion to entering the fortress
    "fortress_to_stronghold",  # fortress to stronghold, in nether blocks (overworld blocks / 8)
    "explosives",            # beds and respawn anchors usable at End enter (held or craftable)
    "iron_pick",             # 1 if an iron (or better) pickaxe was had before the nether, else 0
    "one_cycle_hit",         # 1 if the dragon died within ONE_CYCLE_MS of the first bed/anchor in the End
    # How open the nether is along buckets 3, 5 and 7's routes: % of blocks from y 30 to 90 that
    # are open (air or lava; for 3, a lava ocean is closed), in the chunks between the start and
    # end (see terrain.py).
    "terrain_3", "terrain_5", "terrain_7",
    *BUCKETS,                # real time in each of the model's buckets 1-9 (see PhaseTracker._bucket)
)
# Not kept: fortress enter to the first rod, which is the "Into Fire" advancement's time
# minus the fortress split.
TIME_COLUMNS = ("bastion_time", "first_to_last_rod", *BUCKETS)
STORAGE = {"container.chest", "container.chestDouble", "container.barrel", "container.shulkerBox"}
NETHER_STRUCTURES = {"bastion_remnant", "fortress"}
END_PORTAL_FRAMES = 12

OVERWORLD, NETHER, END = "minecraft:overworld", "minecraft:the_nether", "minecraft:the_end"


# ---- What items are made of -------------------------------------------------------------

RAW = ("planks", "other_blocks", "iron", "gold", "diamonds", "cobblestone", "food")

WOODS = ("oak", "spruce", "birch", "jungle", "acacia", "dark_oak", "crimson", "warped")
_TOOL = {"pickaxe": 3, "axe": 3, "shovel": 1, "sword": 2, "hoe": 2}       # material in each
_TOOL_STICKS = {"pickaxe": 2, "axe": 2, "shovel": 2, "sword": 1, "hoe": 2}
_ARMOR = {"helmet": 5, "chestplate": 8, "leggings": 7, "boots": 4}


def _made_of():
    m = {}
    for wood in WOODS:
        m[f"{wood}_planks"] = {"planks": 1}
        for log in ("log", "wood", "stem", "hyphae"):
            m[f"{wood}_{log}"] = m[f"stripped_{wood}_{log}"] = {"planks": 4}
        m[f"{wood}_boat"] = {"planks": 5}
    m["stick"] = {"planks": 0.5}
    m["crafting_table"] = {"planks": 4}
    m["chest"] = {"planks": 8}
    m["bowl"] = {"planks": 0.75}
    m["shield"] = {"planks": 6, "iron": 1}
    for tool, n in _TOOL.items():
        sticks = {"planks": _TOOL_STICKS[tool] / 2}
        m[f"wooden_{tool}"] = {"planks": n + sticks["planks"]}
        m[f"stone_{tool}"] = {"cobblestone": n, **sticks}
        m[f"iron_{tool}"] = {"iron": n, **sticks}
        m[f"golden_{tool}"] = {"gold": n, **sticks}
        m[f"diamond_{tool}"] = {"diamonds": n, **sticks}
    for piece, n in _ARMOR.items():
        m[f"iron_{piece}"] = {"iron": n}
        m[f"golden_{piece}"] = {"gold": n}
        m[f"diamond_{piece}"] = {"diamonds": n}
    for bucket in ("bucket", "water_bucket", "lava_bucket", "milk_bucket", "cod_bucket", "salmon_bucket",
                   "pufferfish_bucket", "tropical_fish_bucket"):
        m[bucket] = {"iron": 3}
    m.update({
        "iron_ingot": {"iron": 1}, "iron_nugget": {"iron": 1 / 9}, "iron_block": {"iron": 9},
        "flint_and_steel": {"iron": 1}, "shears": {"iron": 2}, "compass": {"iron": 4},
        "heavy_weighted_pressure_plate": {"iron": 2}, "iron_door": {"iron": 2}, "iron_trapdoor": {"iron": 4},
        "hopper": {"iron": 5, "planks": 8}, "minecart": {"iron": 5}, "cauldron": {"iron": 7},
        "light_weighted_pressure_plate": {"gold": 2},
        "gold_ingot": {"gold": 1}, "gold_nugget": {"gold": 1 / 9}, "gold_block": {"gold": 9}, "clock": {"gold": 4},
        "diamond": {"diamonds": 1}, "diamond_block": {"diamonds": 9},
        "cobblestone": {"cobblestone": 1}, "furnace": {"cobblestone": 8},
    })
    return m


MADE_OF = _made_of()

FOOD = {
    "apple", "golden_apple", "enchanted_golden_apple", "bread", "carrot", "golden_carrot", "potato",
    "baked_potato", "poisonous_potato", "beetroot", "beetroot_soup", "mushroom_stew", "rabbit_stew",
    "suspicious_stew", "melon_slice", "sweet_berries", "cookie", "pumpkin_pie", "dried_kelp", "honey_bottle",
    "chorus_fruit", "rotten_flesh", "spider_eye",
    "beef", "cooked_beef", "porkchop", "cooked_porkchop", "chicken", "cooked_chicken", "mutton",
    "cooked_mutton", "rabbit", "cooked_rabbit", "cod", "cooked_cod", "salmon", "cooked_salmon",
    "tropical_fish", "pufferfish",
}

# Items that aren't blocks (there's no list of which are in the log, so this is by hand).
_NOT_BLOCKS = {
    "ender_pearl", "ender_eye", "blaze_rod", "blaze_powder", "flint", "string", "gunpowder", "feather",
    "leather", "bone", "bone_meal", "arrow", "spectral_arrow", "tipped_arrow", "bow", "crossbow", "coal",
    "charcoal", "paper", "book", "writable_book", "written_book", "enchanted_book", "wheat", "wheat_seeds",
    "beetroot_seeds", "melon_seeds", "pumpkin_seeds", "emerald", "lapis_lazuli", "redstone", "clay_ball",
    "brick", "nether_brick", "glass_bottle", "experience_bottle", "map", "filled_map", "name_tag", "saddle",
    "lead", "prismarine_shard", "prismarine_crystals", "nautilus_shell", "heart_of_the_sea", "ink_sac",
    "slime_ball", "ghast_tear", "magma_cream", "quartz", "netherite_ingot", "netherite_scrap",
    "totem_of_undying", "trident", "turtle_helmet", "scute", "phantom_membrane", "rabbit_hide", "rabbit_foot",
    "honeycomb", "minecart", "carrot_on_a_stick", "warped_fungus_on_a_stick", "firework_rocket",
    "firework_star", "armor_stand", "item_frame", "painting", "snowball", "egg", "fire_charge",
    "shulker_shell", "dragon_breath", "popped_chorus_fruit", "glowstone_dust", "sugar", "fermented_spider_eye",
    "glistering_melon_slice", "fishing_rod", "potion", "splash_potion", "lingering_potion", "elytra",
    "chainmail_helmet", "chainmail_chestplate", "chainmail_leggings", "chainmail_boots", "leather_helmet",
    "leather_chestplate", "leather_leggings", "leather_boots", "netherite_helmet", "netherite_chestplate",
    "netherite_leggings", "netherite_boots", "debug_stick", "knowledge_book", "nether_star", "flower_banner_pattern",
}
# Placed but not building blocks: beds and anchors explode (they're counted on their own).
_NOT_BUILDING = ("_bed", "respawn_anchor")


def _short(item_id):
    return item_id.split(":", 1)[-1]


_ITEM_SUFFIXES = ("_spawn_egg", "_dye", "_boat", "_minecart", "_horse_armor", "_banner_pattern", "_pickaxe",
                  "_axe", "_shovel", "_hoe", "_sword", "_bucket", "_helmet", "_chestplate", "_leggings", "_boots",
                  "_ingot", "_nugget")
_ITEMS_MADE = {"stick", "bowl", "shield", "flint_and_steel", "shears", "compass", "clock", "diamond", "bucket"}


def is_block(item_id):
    """Whether an item is placed as a block (a guess for items not listed above)."""
    name = _short(item_id).split("[")[0]
    return not (name in _NOT_BLOCKS or name in FOOD or name in _ITEMS_MADE
                or name.endswith(_ITEM_SUFFIXES) or name.startswith("music_disc_"))


def raw_materials(slots):
    """{RAW name: amount} for an inventory ({slot: (item id, count)}), with tools and other things
    crafted counted as what they're made of (a bucket is 3 iron), and blocks that aren't any of
    them as other_blocks. Also {RAW name: {item: count}}, what each amount is made up of."""
    totals, parts = defaultdict(float), defaultdict(lambda: defaultdict(int))
    for item_id, count in slots.values():
        name = _short(item_id)
        if name in FOOD:
            made = {"food": 1}
        elif name in MADE_OF:
            made = MADE_OF[name]
        elif is_block(item_id) and not name.endswith(_NOT_BUILDING):
            made = {"other_blocks": 1}
        else:
            continue
        for raw, n in made.items():
            totals[raw] += n * count
            parts[raw][name] += count
    return ({raw: round(totals[raw], 1) for raw in RAW},
            {raw: dict(sorted(parts[raw].items(), key=lambda p: -p[1])) for raw in RAW if parts[raw]})


# ---- The ghost ----------------------------------------------------------------------------

class Ghost:
    """The player's position each tick: times (ms) and x, z."""

    def __init__(self, records):
        self.times = [r[0] for r in records]
        self.x = [r[1] for r in records]
        self.z = [r[3] for r in records]

    @classmethod
    def read(cls, hermes_dir, first_time=None):
        """The ghost in a world's hermes folder, or None if there isn't one in a known format."""
        try:
            path = max((hermes_dir / "ghosts").glob("*.ghost"), key=lambda p: p.stat().st_size, default=None)
            data = path.read_bytes() if path else b""
        except OSError:
            return None
        if not data or len(data) % GHOST_RECORD.size:
            return None
        records = list(GHOST_RECORD.iter_unpack(data))
        # Check it's what it should be: times near the play log's, in order.
        if first_time is not None and abs(records[0][0] - first_time) > 24 * 3600 * 1000:
            return None
        if any(b[0] < a[0] for a, b in zip(records[:50], records[1:51])):
            return None
        return cls(records)

    def position(self, time):
        """Where the player was at a time (ms): the last tick at or before it, or None if the
        ghost has no tick within GHOST_GAP_MS of it."""
        k = bisect.bisect_right(self.times, time) - 1
        if k < 0 or time - self.times[k] > GHOST_GAP_MS:
            return None
        return {"x": self.x[k], "z": self.z[k]}


# ---- The play log -------------------------------------------------------------------------

def _xz(position):
    return {"x": position["x"], "z": position["z"]} if position else None


def straight(a, b):
    """Blocks between two {x, z} points in a straight line, or None if either is unknown."""
    return round(math.hypot(a["x"] - b["x"], a["z"] - b["z"])) if a and b else None


class PhaseTracker:
    """Follows a play log (event by event) for the run page's overworld, nether, stronghold
    and End sections; summary() puts it together, with distances from the ghost.
    Stops at opening to LAN, like the item counts."""

    def __init__(self):
        self.lan = False
        self.dimension = OVERWORLD
        self.structures = set()
        self.slots = {}                  # slot -> (item id, count)
        self.igt = 0
        self.death_at = None
        self.spawn = None                # where the player first appeared in the world
        # Overworld, until the nether is first entered.
        self.visits = []                 # [{"structure", "enter", "leave", "looted"}]
        self.last_chest_at = None
        self.chest_visits = None         # the visits a chest open right now is in (None: none open)
        self.last_chest_close = None     # (time, rta)
        # Chests opened in the overworld before the nether outside any structure Hermes reported:
        # [{"open", "close", "close_igt", "close_rta"}]. A buried treasure's structure is just its
        # chest block, so Hermes never reports the player inside one (see add_buried_treasures).
        self.loose_chests = []
        self.last_exit = None            # (time, igt, structure) leaving the last structure
        self.nether_enter = None         # (time, igt)
        self.portal_in = None            # overworld position going into the nether
        self.portal_out = None           # nether position coming out of that portal
        self.nether_inventory = None
        # Nether.
        self.first_structure = None      # (time, igt, structure)
        self.blocks_used = defaultdict(int)
        self.fortress_enter = None       # (time, igt)
        self.fortress_inventory = None
        self.first_rod_igt = None
        self.last_rod_igt = None
        self.bastion = []                # [[enter igt, leave igt or None]]
        self.bastion_exit_inventory = None  # leaving the bastion the last time, before leaving the nether
        self.exits = []                  # nether -> overworld: (time, nether position, overworld position)
        # Stronghold and the End.
        self.stronghold_enter = None     # time
        self.end_enter = None            # time
        self.eyes_used = 0
        self.eyes_back = 0
        # Real time (SpeedRunIGT's RTA, ms) in each of the model's buckets ("pre": before the nether,
        # split into buckets 1 and 2 at the last structure exit).
        self.rta = 0
        self.time_in = defaultdict(float)
        self.last_exit_rta = None
        self.respawned_at = None
        self.bastion_left = None         # (time, rta, bucket) leaving the bastion
        self.bastion_exit_before_fortress = None  # time
        self.end_slots = None
        self.iron_pick = False
        # The End: when each bed and anchor was placed (a bed blows up as it's placed; one broken
        # again, e.g. to land on, is taken off). An anchor's placement is the only time known for
        # it, and it's often placed well before it's blown up.
        self.end_beds = []               # rta
        self.end_anchors = []            # rta
        self.dragon_killed_rta = None    # only when the player gets the kill (not a bed or anchor)
        self.end_exit_rta = None         # through the exit portal: the dragon is dead

    def event(self, event):
        kind, data, now = event.get("type"), event.get("data") or {}, event.get("time") or 0
        if kind == "game_info" and data.get("open_to_lan"):
            self.lan = True
        if self.lan:
            return
        igt = (event.get("speedrunigt") or {}).get("igt")
        if igt:
            self.igt = igt
        rta = (event.get("speedrunigt") or {}).get("rta") or 0
        if rta > self.rta:  # the time since the last event was spent in the bucket of that moment
            if self.rta:
                self.time_in[self._bucket()] += rta - self.rta
            self.rta = rta
        before_nether = self.nether_enter is None
        if kind == "respawn" and not data.get("was_alive"):
            self.respawned_at = now
        if kind == "dimension":
            self._dimension(data, now)
        elif kind == "screen":
            title = (data.get("title") or {})
            chest = self.loose_chests[-1] if self.loose_chests else None
            if chest and chest["close"] is None:  # any next screen (or none) closes the chest
                chest.update(close=now, close_igt=self.igt, close_rta=self.rta)
            if self.chest_visits is not None:  # the same for a chest in a structure
                for visit in self.chest_visits:
                    visit.update(looted_at=now, looted_rta=self.rta)
                self.chest_visits = None
                self.last_chest_close = (now, self.rta)
            if isinstance(title, dict) and title.get("translate") in STORAGE:
                self.last_chest_at = now
                self.chest_visits = self._open_visits()
                for visit in self.chest_visits:
                    visit["looted"] = True
                if before_nether and self.dimension == OVERWORLD and not self._open_visits():
                    self.loose_chests.append({"open": now, "close": None, "close_igt": None, "close_rta": None})
        elif kind == "inside_structures":
            self._structures({s.split(":")[-1] for s in data.get("structures") or []}, now, before_nether)
        elif kind == "stat":
            self._stat(data.get("stat", ""), data.get("diff") or 0, now)
        elif kind == "inventory_slots":
            for slot, item in (data.get("slots") or {}).items():
                if item and item.get("id"):
                    item_id = item["id"]
                    potion = (item.get("tag") or {}).get("Potion")
                    if potion and "potion" in item_id:
                        item_id = f"{item_id}[{_short(potion)}]"
                    self.slots[slot] = (item_id, item.get("Count", 1))
                    if item_id in PICKAXES and before_nether:
                        self.iron_pick = True
                else:
                    self.slots.pop(slot, None)

    def _bucket(self):
        """The model's bucket the run is in right now (see model.py). Every moment goes to one."""
        if self.nether_enter is None:
            return "pre"
        if self.end_enter is not None:
            return 10
        if self.stronghold_enter is not None:
            return 9
        if self.exits:  # after the blind: back in the fortress counts as getting rods
            return 7 if self.dimension == NETHER and "fortress" in self.structures else 8
        if self.dimension == NETHER and "bastion_remnant" in self.structures:
            return 4
        if self.first_structure is None:
            return 3
        if self.first_rod_igt is not None:
            return 7
        if self.fortress_enter is not None:
            return 6
        return 5

    def add_buried_treasures(self, is_treasure):
        """Turn the chests opened outside any reported structure into buried treasure visits,
        where is_treasure(time) says the player's chunk then holds one (from the ghost and the
        world's saved chunks). A visit runs from opening the chest to closing it; opening it
        again extends it."""
        for chest in self.loose_chests:
            if chest["close"] is None:
                continue
            # A chest opened just before Hermes reported a structure belongs to that structure.
            if any(chest["open"] <= v["enter"] <= chest["open"] + STRUCTURE_LAG_MS for v in self.visits):
                continue
            if not is_treasure(chest["open"]):
                continue
            last = self.visits[-1] if self.visits else None
            if last and last["structure"] == "buried_treasure" and chest["open"] - last["leave"] <= SAME_VISIT_MS:
                visit = last
            else:
                visit = {"structure": "buried_treasure", "enter": chest["open"], "looted": True}
                self.visits.append(visit)
            visit.update(leave=chest["close"], leave_rta=chest["close_rta"])
            if self.last_exit is None or chest["close"] >= self.last_exit[0]:
                self.last_exit = (chest["close"], chest["close_igt"], "buried_treasure")
                self.last_exit_rta = chest["close_rta"]
        self.visits.sort(key=lambda v: v["enter"])

    def _open_visits(self):
        return [v for v in self.visits if v["leave"] is None]

    def _dimension(self, data, now):
        old, new = data.get("old_dimension"), data.get("dimension") or self.dimension
        if old is None and self.spawn is None:
            self.spawn = _xz(data.get("position"))
        respawn = self.respawned_at is not None and now - self.respawned_at <= RESPAWN_MS
        if self.bastion and self.bastion[-1][1] is None:
            self.bastion[-1][1] = self.igt  # left the bastion through a portal (or died)
            if old == NETHER and not respawn and not self.exits:
                self.bastion_exit_inventory = dict(self.slots)
        if new == NETHER and self.nether_enter is None and old == OVERWORLD:
            self.nether_enter = (now, self.igt)
            self.portal_in, self.portal_out = _xz(data.get("old_position")), _xz(data.get("position"))
            self.nether_inventory = dict(self.slots)
            inside = [v["structure"] for v in self._open_visits() if v["structure"] not in NOT_LAST_STRUCTURE]
            if inside:  # went in from inside a structure (a ruined portal, say)
                self.last_exit = (now, self.igt, inside[0])
                self.last_exit_rta = self.rta
            for visit in self._open_visits():
                visit["leave"] = now
                visit["leave_rta"] = self.rta
        if old == END and new == OVERWORLD and not respawn and self.end_exit_rta is None:
            self.end_exit_rta = self.rta
        if old == NETHER and new == OVERWORLD and not respawn:
            self.exits.append((now, _xz(data.get("old_position")), _xz(data.get("position"))))
        if new == END and self.end_enter is None:
            self.end_enter = now
            self.end_slots = dict(self.slots)
        self.dimension = new
        self.structures = set()

    def _structures(self, now_inside, now, before_nether):
        left, entered = self.structures - now_inside, now_inside - self.structures
        self.structures = now_inside
        if self.dimension == OVERWORLD and before_nether:
            for name in left:
                for visit in self._open_visits():
                    if visit["structure"] == name:
                        visit["leave"] = now
                        visit["leave_rta"] = self.rta
                if name not in NOT_LAST_STRUCTURE:
                    self.last_exit = (now, self.igt, name)
                    self.last_exit_rta = self.rta
            for name in entered:
                last = next((v for v in reversed(self.visits) if v["structure"] == name), None)
                if last and last["leave"] is not None and now - last["leave"] <= SAME_VISIT_MS:
                    last["leave"] = None  # back in the same one
                else:
                    looted = self.last_chest_at is not None and now - self.last_chest_at <= STRUCTURE_LAG_MS
                    visit = {"structure": name, "enter": now, "leave": None, "leave_rta": None,
                             "looted": looted, "looted_at": None, "looted_rta": None}
                    self.visits.append(visit)
                    if looted and self.chest_visits is not None:  # the chest is still open
                        self.chest_visits.append(visit)
                    elif looted and self.last_chest_close and self.last_chest_close[0] >= self.last_chest_at:
                        visit["looted_at"], visit["looted_rta"] = self.last_chest_close
        if self.dimension == NETHER and self.nether_enter is not None:
            if "bastion_remnant" in entered:
                last = self.bastion[-1] if self.bastion else None
                if last and last[1] is not None and self.igt - last[1] <= BASTION_GAP_MS:
                    self.bastion[-1][1] = None  # only stepped out for a moment
                    if self.bastion_left:  # so that moment counts as in the bastion
                        _, left_rta, bucket = self.bastion_left
                        self.time_in[bucket] -= self.rta - left_rta
                        self.time_in[4] += self.rta - left_rta
                else:
                    self.bastion.append([self.igt, None])
            if "bastion_remnant" in left and self.bastion and self.bastion[-1][1] is None:
                self.bastion[-1][1] = self.igt
                self.bastion_left = (now, self.rta, self._bucket())
                if not self.exits:  # still on the way to the stronghold portal
                    self.bastion_exit_inventory = dict(self.slots)
            if self.first_structure is None and entered & NETHER_STRUCTURES:
                self.first_structure = (now, self.igt, sorted(entered & NETHER_STRUCTURES)[0])
            if self.fortress_enter is None and "fortress" in entered:
                self.fortress_enter = (now, self.igt)
                if self.bastion_left:
                    self.bastion_exit_before_fortress = self.bastion_left[0]
                self.fortress_inventory = dict(self.slots)
        if self.dimension == OVERWORLD and "stronghold" in entered and self.stronghold_enter is None:
            self.stronghold_enter = now

    def _stat(self, stat, diff, now):
        if stat == "minecraft.custom:minecraft.deaths":
            self.death_at = now
        if diff <= 0:
            return
        action, _, item = stat.partition(":")
        item = item.replace("minecraft.", "minecraft:", 1)
        if action == "minecraft.crafted" and item in PICKAXES and self.nether_enter is None:
            self.iron_pick = True
        if self.dimension == END:
            if action == "minecraft.used" and item.endswith("_bed"):
                self.end_beds.append(self.rta)
            elif action == "minecraft.mined" and item.endswith("_bed") and self.end_beds:
                self.end_beds.pop()  # placed and broken again: not a blast
            elif action == "minecraft.used" and item == "minecraft:respawn_anchor":
                self.end_anchors.append(self.rta)
            if stat == "minecraft.killed:minecraft.ender_dragon" and self.dragon_killed_rta is None:
                self.dragon_killed_rta = self.rta
        if (action == "minecraft.used" and self.dimension == NETHER and self.nether_enter is not None
                and self.first_structure is None and is_block(item) and not item.endswith(_NOT_BUILDING)):
            self.blocks_used[_short(item)] += diff
        if (item == "minecraft:blaze_rod" and action == "minecraft.picked_up" and self.fortress_enter
                and self.dimension == NETHER and not self.exits):
            if self.first_rod_igt is None:
                self.first_rod_igt = self.igt
            self.last_rod_igt = self.igt
        if item == "minecraft:ender_eye" and "stronghold" in self.structures and self.dimension == OVERWORLD:
            if action == "minecraft.used":
                self.eyes_used += diff
            elif action == "minecraft.picked_up":
                self.eyes_back += min(diff, self.eyes_used - self.eyes_back)

    def summary(self, ghost):
        """The run's sections, as stored in runs.csv (numbers in ms and blocks), with
        "columns": the numbers runs.csv also keeps as columns (see COLUMNS)."""
        at = ghost.position if ghost else (lambda time: None)
        columns = dict.fromkeys(COLUMNS)
        overworld = {"structures": [{"structure": v["structure"], "looted": v["looted"]} for v in self.visits]}
        # World spawn to each structure entered, in turn, up to the last one.
        route = [self.spawn] + [at(v["enter"]) for v in self.visits if v["structure"] not in NOT_LAST_STRUCTURE]
        if len(route) > 1 and all(route):
            columns["spawn_to_structures"] = sum(straight(a, b) for a, b in zip(route, route[1:]))
        if not self.nether_enter and (reference := self._seed_structure()):
            columns["last_structure"] = reference["structure"]  # the seed type so far (runs page)
        if self.nether_enter:
            enter_time, enter_igt = self.nether_enter
            overworld["materials"], overworld["materials_from"] = raw_materials(self.nether_inventory)
            if self.last_exit:
                time, igt, name = self.last_exit
                overworld["to_nether"] = {"structure": name, "ms": max(0, enter_igt - igt),
                                          "distance": 0 if time == enter_time else straight(at(time), self.portal_in)}

        nether = {}
        if self.nether_enter:
            if self.first_structure:
                time, igt, name = self.first_structure
                columns["to_first_structure"] = straight(self.portal_out, at(time))
                nether["to_structure"] = {"structure": name, "ms": igt - self.nether_enter[1],
                                          "distance": columns["to_first_structure"],
                                          "blocks": sum(self.blocks_used.values()),
                                          "blocks_from": dict(sorted(self.blocks_used.items(), key=lambda p: -p[1]))}
        # Slot (0-8 hotbar, 9-35 the rest, 36-39 armor feet to head, 40 offhand) -> [item, count]:
        # leaving the bastion (after trading, whichever structure came first), or entering the
        # fortress in a run without a bastion.
        shown = self.bastion_exit_inventory or (self.fortress_enter and self.fortress_inventory)
        if shown:
            nether["inventory"] = {"at": "bastion_exit" if self.bastion_exit_inventory else "fortress_enter",
                                   "slots": {slot: [_short(item_id), count] for slot, (item_id, count) in shown.items()}}
        if self.fortress_enter:
            if self.first_rod_igt is not None:
                nether["first_rod_ms"] = self.first_rod_igt - self.fortress_enter[1]
                columns["first_to_last_rod"] = self.last_rod_igt - self.first_rod_igt
        if self.bastion:
            columns["bastion_time"] = sum((leave if leave is not None else self.igt) - enter
                                          for enter, leave in self.bastion)

        # The blind portal (the first way out of the nether) to the stronghold portal (the
        # last way out before the stronghold): the same one unless the player went back in.
        until = self.stronghold_enter or self.end_enter
        exits = [e for e in self.exits if until is not None and e[0] <= until]
        if exits and exits[0][1] and exits[-1][1]:
            blind, portal = exits[0][1], exits[-1][1]
            apart = math.hypot(blind["x"] - portal["x"], blind["z"] - portal["z"])
            nether["blind"] = {"blind": blind, "portal": portal,
                               "nether_distance": round(apart), "distance": round(apart * 8)}

        if self.nether_enter:
            self._model_columns(columns, at)

        stronghold = {}
        if self.stronghold_enter is not None:
            stronghold["eyes_placed"] = min(END_PORTAL_FRAMES, self.eyes_used - self.eyes_back)
        return {"overworld": overworld, "nether": nether, "stronghold": stronghold,
                "distances": ghost is not None, "columns": columns}

    def terrain_routes(self, at):
        """{bucket: (start, end, a lava ocean counts as closed)} in nether coordinates, for the
        buckets the run got through: 3 portal to bastion (bastion first, usually before fire
        resistance, so a lava ocean has to be bridged), 5 bastion to fortress, 7 fortress to the
        blind portal."""
        routes = {}
        if self.first_structure and self.first_structure[2] == "bastion_remnant":
            routes[3] = (self.portal_out, at(self.first_structure[0]), True)
        if self.bastion_exit_before_fortress and self.fortress_enter:
            routes[5] = (at(self.bastion_exit_before_fortress), at(self.fortress_enter[0]), False)
        if self.fortress_enter and self.exits:
            routes[7] = (at(self.fortress_enter[0]), self.exits[0][1], False)
        return routes

    def _seed_structure(self):
        """The visit that sets the seed type: the last looted of the five MCSR Ranked seed types,
        except that a ruined portal only counts when it's the only one looted (a portal looted
        after a village, say, is on the way to the nether: it's a village seed). None if none."""
        looted = [v for v in self.visits if v["structure"] in SEED_TYPES and v["looted"]]
        main = [v for v in looted if v["structure"] != "ruined_portal"]
        return (main or looted or [None])[-1]

    def _model_columns(self, columns, at):
        """The performance model's inputs (see COLUMNS and model.py)."""
        # Bucket 1 ends on leaving the seed-type structure, or for a ruined portal on closing its
        # chest (the portal is often lit right there, so the player may never leave it). Without
        # one the run is structureless, all of it in bucket 2.
        reference = self._seed_structure()
        columns["last_structure"] = reference["structure"] if reference else ""
        end, end_rta = (reference["leave"], reference["leave_rta"]) if reference else (None, None)
        if reference and reference["structure"] == "ruined_portal" and reference.get("looted_rta") is not None:
            end, end_rta = reference["looted_at"], reference["looted_rta"]
        first = (end_rta or self.time_in["pre"]) if reference else 0
        if reference:
            columns["spawn_to_structure"] = straight(self.spawn, at(reference["enter"]))
            left = end
            columns["structure_to_portal"] = (0 if left is not None and left == self.nether_enter[0]
                                              else straight(at(left), self.portal_in) if left else None)
        columns["bucket_1"] = round(first)
        columns["bucket_2"] = round(max(0, self.time_in["pre"] - first))
        for i in range(3, 10):
            columns[f"bucket_{i}"] = round(self.time_in[i])
        if self.bastion_exit_before_fortress and self.fortress_enter:
            columns["bastion_to_fortress"] = straight(at(self.bastion_exit_before_fortress),
                                                      at(self.fortress_enter[0]))
        if self.fortress_enter and self.stronghold_enter is not None:
            fortress, stronghold = at(self.fortress_enter[0]), at(self.stronghold_enter)
            if fortress and stronghold:
                columns["fortress_to_stronghold"] = straight(
                    fortress, {"x": stronghold["x"] / 8, "z": stronghold["z"] / 8})
        if self.end_slots is not None:
            columns["explosives"] = usable_explosives(self.end_slots)
        columns["iron_pick"] = int(self.iron_pick)
        # One cycle: the dragon died within ONE_CYCLE_MS of the first blast. Blasts are the beds
        # (anchors only when no bed was used: their placement can come long before they blow up).
        # A bed or anchor kill isn't credited to the player (no kill stat), so leaving through the
        # exit portal means the last blast killed it.
        blasts = self.end_beds or self.end_anchors
        killed = self.dragon_killed_rta
        if killed is None and self.end_exit_rta is not None and blasts:
            killed = blasts[-1]
        if killed is not None:  # no beds or anchors used in the End: no one cycle
            columns["one_cycle_hit"] = int(bool(blasts) and killed - blasts[0] <= ONE_CYCLE_MS)


def usable_explosives(slots):
    """Beds and respawn anchors held, plus as many as could be crafted from what's held: a bed
    from 3 wool and 3 planks, an anchor from 6 crying obsidian and 3 glowstone (4 dust each)."""
    count = defaultdict(int)
    for item_id, n in slots.values():
        count[_short(item_id)] += n
    beds = sum(n for name, n in count.items() if name.endswith("_bed"))
    wool = sum(n for name, n in count.items() if name.endswith("_wool"))
    planks = sum(n for name, n in count.items() if name.endswith("_planks"))
    glowstone = count["glowstone"] + count["glowstone_dust"] // 4
    return (beds + count["respawn_anchor"] + min(wool // 3, planks // 3)
            + min(count["crying_obsidian"] // 6, glowstone // 3))
