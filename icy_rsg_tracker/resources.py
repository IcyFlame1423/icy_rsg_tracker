"""A run's key resources, from the item statistics SpeedRunIGT saves with each record.

"Collected" is items picked up minus items dropped, so dropping something and picking it
back up doesn't count twice. Items taken straight out of a chest aren't in the game's
statistics, so where the game says more was crafted than the pickups allow (string from a
chest, say), the crafted amount wins.

Deaths: everything dropped on death and picked up again counts as picked up again. The
statistics are only totals for the run, so the true amount is estimated (see estimate()),
allowing for what was likely used up before each death (see USAGE).
"""

import math

from .records import parse_record

FIRE_RES_MS = 180_000           # a fire resistance potion lasts 3:00 (drinkable and splash alike)
FIRE_RES_LEAD_MS = 60_000       # drunk a minute before entering the fortress
MIN_RODS_FOR_END = 6            # 12 eyes of ender need 6 blaze rods

COLORS = ["white", "orange", "magenta", "light_blue", "yellow", "lime", "pink", "gray",
          "light_gray", "cyan", "purple", "blue", "brown", "green", "red", "black"]
WOODS = ["oak", "spruce", "birch", "jungle", "acacia", "dark_oak", "crimson", "warped"]
# Logs, wood and stems (stripped or not) each make 4 planks.
LOGS = [f"{prefix}{wood}_{kind}" for wood in WOODS for prefix in ("", "stripped_")
        for kind in (("stem", "hyphae") if wood in ("crimson", "warped") else ("log", "wood"))]


def _stats(record):
    """{category: {item: count}} summed over the record's players, without "minecraft:"."""
    out = {}
    for player in (record.get("stats") or {}).values():
        for category, values in (player.get("stats") or {}).items():
            bucket = out.setdefault(category.removeprefix("minecraft:"), {})
            for item, n in values.items():
                key = item.removeprefix("minecraft:")
                bucket[key] = bucket.get(key, 0) + n
    return out


def pickup_divisor(deaths, completed):
    """How many times each item was picked up, if nothing was used before any death.

    Picking your items back up after a death counts them as picked up again. Completed
    with n deaths: picked up again after every death -> counted n + 1 times. Reset with
    n deaths: left behind at the last death -> counted n times (1 death: unchanged).
    """
    if deaths <= 0:
        return 1
    return deaths + 1 if completed else deaths


def estimate(picked, used_before):
    """The amount actually collected, from pickups (minus drops) that include re-pickups.

    used_before: for each death whose items were picked up again, how many had been used
    by then. Assuming everything collected was held at each death, each re-pickup adds
    (total - used) more, so picked = total + sum(total - used_i), and
    total = (picked + sum(used_i)) / (1 + deaths picked up again).
    A death where everything was already used adds nothing, so it's left out and the
    sum worked out again.
    """
    counted = list(used_before)
    while True:
        total = (picked + sum(counted)) / (1 + len(counted))
        kept = [u for u in counted if u < total]
        if len(kept) == len(counted):
            return max(0, round(total))
        counted = kept


def _usage(splits):
    """{item: used(death ms)}: how many were likely used up by a given in-game time."""
    entered = sorted(t for t in (splits.get("bastion"), splits.get("fortress")) if t is not None)
    structure1, structure2 = (entered + [None, None])[:2]
    fortress, blind, stronghold = splits.get("fortress"), splits.get("blind"), splits.get("stronghold")

    def obsidian(t):
        # 10 for the blind portal, another 10 by the stronghold (e.g. for the end portal room).
        if stronghold is not None and t >= stronghold:
            return 20
        return 10 if blind is not None and t >= blind else 0

    def fire_resistance(t):
        # One potion always active from a minute before the fortress to the stronghold.
        if fortress is None:
            return 0
        start = fortress - FIRE_RES_LEAD_MS
        if t <= start:
            return 0
        end = min(t, stronghold) if stronghold is not None else t
        return max(1, math.ceil((end - start) / FIRE_RES_MS))

    def stretch(t, start, finish):
        # 2 pearls per stretch; 1 if the death came partway through it.
        if start is None or t <= start:
            return 0
        return 2 if finish is not None and t >= finish else 1

    def ender_pearls(t):
        return stretch(t, structure1, structure2) + stretch(t, blind, stronghold)

    return {"obsidian": obsidian, "fire_resistance": fire_resistance, "ender_pearls": ender_pearls}


def resources(record, death_times=None, death_resets=None):
    """{name: {"count", "detail"}} for blaze_rods, ender_pearls, beds, respawn_anchors,
    fire_resistance and obsidian (detail: how the count was worked out), plus
    "pickup_divisor" (what pickups were divided by if nothing was used; 1: no deaths) and
    "death_times_known" (whether usage before each death could be allowed for).

    death_times: in-game ms of each death (from the game log), or None if unknown.
    death_resets: for each death, whether it respawned at a bed/anchor (or None).
    """
    stats = _stats(record)
    picked, dropped, crafted = (stats.get(c, {}) for c in ("picked_up", "dropped", "crafted"))
    deaths = stats.get("custom", {}).get("deaths", 0)
    completed = bool(record.get("is_completed"))
    divisor = pickup_divisor(deaths, completed)
    repicked = divisor - 1  # deaths whose items were picked up again
    known = death_times is not None and len(death_times) == deaths and deaths > 0
    splits = parse_record(record, "").splits
    usage = _usage(splits) if known else {}
    # A death reset in the nether means a respawn anchor was placed (beds explode there),
    # and it's left behind: 6 crying obsidian and 3 glowstone (12 dust) used up.
    nether, blind = splits.get("nether"), splits.get("blind")
    anchor_resets = sorted(t for t, reset in zip(death_times or [], death_resets or []) if reset and known
                           and nether is not None and t >= nether and (blind is None or t < blind))

    def anchors_used(t):
        return sum(1 for r in anchor_resets if r <= t)
    # The deaths whose items were picked up again: all of them, or all but the last on a reset.
    repicked_times = sorted(death_times)[:repicked] if known else []

    def net(*items):
        return max(0, sum(picked.get(i, 0) - dropped.get(i, 0) for i in items))

    def got(*items, use=None):
        # Crafted amounts aren't affected by deaths, so only pickups are estimated.
        if use and known:
            return estimate(net(*items), [use(t) for t in repicked_times])
        return estimate(net(*items), [0] * repicked)

    out = {"pickup_divisor": divisor, "death_times_known": known}
    # Entering the End takes 12 eyes of ender, so 6 blaze rods at least.
    rods = got("blaze_rod")
    if splits.get("end") is not None:
        rods = max(rods, MIN_RODS_FOR_END)
    out["blaze_rods"] = {"count": rods, "detail": "Blaze rods collected"}
    out["ender_pearls"] = {"count": got("ender_pearl", use=usage.get("ender_pearls")),
                           "detail": "Ender pearls collected"}

    # Beds: 3 wool of one colour + 3 planks of any wood. String makes white wool (4 each).
    string = got("string")
    white_wool = got("white_wool") + max(string // 4, crafted.get("white_wool", 0))
    wool = {c: got(f"{c}_wool") for c in COLORS}
    wool["white"] = white_wool
    wool_beds = sum(n // 3 for n in wool.values())
    planks = sum(got(f"{w}_planks") for w in WOODS) + max(
        4 * sum(got(log) for log in LOGS), sum(crafted.get(f"{w}_planks", 0) for w in WOODS))
    # Beds found (e.g. in a village) are beds both mined and picked up. Picked up alone
    # isn't enough: everything dropped on death and picked up again counts as picked up.
    mined = stats.get("mined", {})
    found_beds = sum(min(got(f"{c}_bed"), mined.get(f"{c}_bed", 0)) for c in COLORS)
    made = min(wool_beds, planks // 3)
    crafted_beds = sum(crafted.get(f"{c}_bed", 0) for c in COLORS)
    beds = max(made, crafted_beds) + found_beds
    parts = [f"{white_wool} white wool" + (f" ({string} string)" if string else "")]
    other_wool = sum(n for c, n in wool.items() if c != "white")
    if other_wool:
        parts.append(f"{other_wool} other wool")
    parts.append(f"{planks} planks")
    if found_beds:
        parts.append(f"{found_beds} beds found")
    out["beds"] = {"count": beds, "detail": "Beds you could make: " + ", ".join(parts)}

    # Respawn anchors: 6 crying obsidian + 3 glowstone (4 dust each).
    crying = got("crying_obsidian", use=lambda t: 6 * anchors_used(t))
    dust = got("glowstone_dust", use=lambda t: 12 * anchors_used(t))
    glowstone = got("glowstone") + max(dust // 4, crafted.get("glowstone", 0))
    anchors = max(min(crying // 6, glowstone // 3), crafted.get("respawn_anchor", 0)) + got("respawn_anchor")
    out["respawn_anchors"] = {
        "count": anchors,
        "detail": f"Respawn anchors you could make: {crying} crying obsidian, {glowstone} glowstone ({dust} dust)"}

    # Fire resistance: the only potions piglins barter (drinkable and splash).
    potions = got("potion", "splash_potion", use=usage.get("fire_resistance"))
    out["fire_resistance"] = {"count": potions, "detail": "Fire resistance potions collected"}
    out["obsidian"] = {"count": got("obsidian", use=usage.get("obsidian")), "detail": "Obsidian collected"}
    return out
