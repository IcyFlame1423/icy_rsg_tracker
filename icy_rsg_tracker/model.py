"""The run performance model: how many seconds a completed run lost against a top player on
the same seed.

    S = sum over buckets i of (t_i - T*_i)
    T*_i = W_i * f_i + sum over shortages k of gamma_ik * x_k   (+ zeta * (C - W_10) for the End)

The End (bucket 10) depends on the explosives (beds, anchors) at End enter, E:
- E >= 3: a zero cycle (E >= 5) or one cycle is expected. If the one cycle killed the dragon, the
  End time is capped at C (a bad perch isn't punished); if it missed, the whole End time counts.
- E <= 2: a two cycle (or more perches), whose top-player median M is expected; the time between
  M and the 90th percentile P is free (bad luck), and time past P counts again (a failed cycle):
  t_10 = min(t, M) + max(0, t - P).

0 is a run by a top player executed as well as they can (their median time in every bucket); a
typical top-player finish scores about +25 s. The coefficients were fitted on MCSR Ranked: the 30
top players by Elo, 20 recent matches each (4 per overworld seed type), see the model document.
Every value is in seconds (distances in blocks).
"""

from .timefmt import parse_time

# ---- Fitted and assumed coefficients ----

C = 90.0  # End cap: a zero cycle not done by then counts as a one cycle (if the one cycle is hit)
# With 2 explosives or fewer, more perches: (median, 90th percentile) of a top player's End fight.
# 2: a two cycle (T_Wagz's End fight time analysis: 3:20 median, 4:31 at the 90th percentile).
# 1 and 0: each further perch takes 1:19 longer, the two cycle's median over a full bow's (2:01).
MULTI_CYCLE = {2: (200.0, 271.0), 1: (279.0, 350.0), 0: (358.0, 429.0)}

# W_1 (spawn to leaving the last overworld structure) and W_2 (the rest of the time to nether
# enter: the Ranked median nether enter minus W_1), by the last overworld structure's type.
# W_1 from when the top players looted the structure (their first time, Ranked timelines):
# - buried treasure: Acquire Hardware (an iron ingot from the chest), median 16.4 s, plus 0.3 s
#   to close the chest (the median gap on the tracker's own buried treasure runs);
# - shipwreck: Acquire Hardware at the first chest, median 16.3 s, plus 7.5 s for the second
#   chest: getting to it, 1 s to loot it and swimming out (the median on the tracker's own
#   underwater shipwrecks with two chests, no blocks broken and no map chest);
# - ruined portal: Ice Bucket Challenge (obsidian from the chest), median 8.5 s, leaving out the
#   matches where it came after 60 s (obsidian from the bastion instead: none from 36 to 89 s);
# - desert temple: 31.05 s inside (entering to leaving, the average of 4 playoff runs) plus 8 s
#   to walk there (40 blocks, the average within 5 chunks, at 0.20 s per block);
# - village: assumed.
OVERWORLD = {
    "village": (105.0, 25.6),
    "shipwreck": (23.8, 91.3),
    "desert_pyramid": (39.0, 69.6),
    "ruined_portal": (8.5, 53.3),
    "buried_treasure": (16.7, 80.2),
    # Structureless (no structure of the five looted): iron mined in a cave and smelted. Not in
    # MCSR Ranked; estimated from Couriway's 100K no-reset runs (no deaths, final time within
    # the Tukey fences): his nether entry is a near-constant ~197 s behind top players' on the
    # four structure types he plays, so his structureless median (6:16) less that gap: 2:59
    # (95% interval 2:53-3:06).
    "": (0.0, 179.0),
}
STRUCTURE_NAMES = {"village": "village", "shipwreck": "shipwreck", "desert_pyramid": "desert temple",
                   "ruined_portal": "ruined portal", "buried_treasure": "buried treasure",
                   "": "no structure (structureless)"}
W = {3: 31.6, 4: 120.0, 5: 26.0, 6: 17.1, 7: 55.0, 8: 92.7, 9: 26.5, 10: 51.7}

# Seed difficulty f = (alpha + beta d) / (alpha + beta d_bar), from quantile fits on Ranked.
FITS = {  # bucket: (alpha, beta per block, average distance d_bar)
    3: (3.85, 0.2564, 112.0),     # nether enter to bastion; d = portal to bastion, 0-224 blocks
    5: (0.0, 0.2031, 128.0),      # bastion to fortress; d = bastion to fortress, 0-256 blocks
    # First rod to blind; n = fortress to stronghold in nether blocks, distributed as simulated for
    # bucket 8 (median 168). Fitted on its own the fixed time comes out below zero (-6 s), so it's
    # 0 and the time per block makes a median seed take the Ranked median (55.0 s / 168.1).
    7: (0.0, 0.3271, 168.125),
    # Blind to stronghold; d = fortress to stronghold in overworld blocks (8 n). The distances
    # on Ranked seeds were simulated: bastion within 10 chunks of 0,0 in the nether, fortress
    # within 16 chunks of the bastion, and the nearest of the first ring's 3 strongholds
    # (1280-2816 blocks from 0,0, 120 degrees apart): median 1345 blocks, 5-95% 445-2059.
    8: (6.34, 0.06953, 1345.0),
}
# Terrain along buckets 3, 5 and 7's routes (terrain.py: % of the chunks' blocks from y 30 to 90
# that are open). Levels set from 20 blind travels rated by hand, which the cutoffs match 17/20;
# the multipliers on the time per block from fitting those runs' travel times (each 10 points
# more open: about 8% faster per block; uncertain, so rounded), the same for all three buckets.
TERRAIN_CUTOFFS = (30.0, 50.0)       # below 30% open: poor; below 50%: average; else good
TERRAIN = {"good": 0.9, "average": 1.1, "poor": 1.25}


def terrain_level(open_percent):
    if open_percent is None:
        return None
    return "poor" if open_percent < TERRAIN_CUTOFFS[0] else "average" if open_percent < TERRAIN_CUTOFFS[1] else "good"


# The overworld: distance doesn't come out of a fit (looting and finding lava swamp it), so the
# time per block is a travel speed: (beta, spawn -> structure range, structure -> portal range),
# the ranges from MCSR Ranked's seed filter (distances assumed evenly spread over them).
OVERWORLD_TRAVEL = {
    "village": (0.20, 112.0, 96.0),          # within 7 chunks; lava pools near (taken as 96 blocks)
    "desert_pyramid": (0.20, 80.0, 96.0),    # within 5 chunks; lava pools near
    "ruined_portal": (0.20, 48.0, None),     # within 3 chunks; the portal is the structure
    "shipwreck": (0.15, 64.0, 160.0),        # within 4 chunks; magma ravines within 10 chunks
    "buried_treasure": (0.15, 80.0, 160.0),  # within 5 chunks; magma ravines within 10 chunks
}
BLAZE_S = 6.25   # per blaze killed at a spawner (4 blazes per 25 s cycle)
STRAYS = 3       # the first blazes are strays around the fortress, at no extra time

# Resource allowances gamma (seconds) by bucket.
ONE_FIRE_RES = {7: 10.0}
NO_FIRE_RES = {5: 20.0, 7: 10.0}
FEW_EXPLOSIVES = {10: 50.0}          # fewer than 5 usable at End enter
EXPLOSIVES_NEEDED = 5
PER_TRAVEL_PEARL = {5: 4.0, 6: 1.0, 8: 4.0, 9: 1.0}
COMFORTABLE_PEARLS = 21
NO_IRON_PICK = {4: 19.8}             # fitted: ruined portal bastions, which give no iron pick

BUCKET_NAMES = {
    1: "Spawn to last overworld structure", 2: "Last structure to nether enter",
    3: "Nether enter to bastion", 4: "Bastion", 5: "Bastion to fortress", 6: "Fortress to first rod",
    7: "First rod to blind", 8: "Blind to stronghold", 9: "Stronghold to End", 10: "End",
}

# ---- Ranks: which MCSR Ranked tier a run (or a part of it) is as good as ----
# From 590 completed Ranked matches (end of season 11): 10 per overworld seed type for each tier
# from Iron I to Netherite, won by a player whose Elo before the match was in the middle of the
# tier (its center +- 20% of its width; Netherite 2000-2200). Buried treasure below Emerald (those
# tiers don't get the seeds) is their shipwreck runs with the overworld 0.82x as long (buried
# treasure / shipwreck on Emerald and up). Each run scored like the top players (an average seed).
# Every level is a ratio, time / a top player's time, so a tier's time scales with the seed: a
# longer distance costs a slower player more. Each tier's median ratio is fitted with a logistic
# curve in Elo (R2 0.88-0.99) and read at the middle of the tier:
# - total: the finish (the End capped, as in the score) / the top players' total;
# - the parts (see RANK_PARTS); the End uncapped (Ranked has no explosive counts).
# Top 30 is the top-player sample's own medians. Below Iron I is Coal (its runs vary too much).
# (tier, {"total" or part: time / top-player time}), worst first.
RANKS = [
    ("Iron I", {"total": 2.654, "1+2": 2.09, "4+5": 2.291, "7": 1.993, "8": 2.681, "9": 5.178, "End": 2.793}),
    ("Iron II", {"total": 2.396, "1+2": 1.948, "4+5": 2.121, "7": 1.918, "8": 2.345, "9": 4.4, "End": 2.78}),
    ("Iron III", {"total": 2.177, "1+2": 1.819, "4+5": 1.959, "7": 1.846, "8": 2.075, "9": 3.762, "End": 2.751}),
    ("Gold I", {"total": 1.992, "1+2": 1.704, "4+5": 1.809, "7": 1.776, "8": 1.858, "9": 3.239, "End": 2.695}),
    ("Gold II", {"total": 1.834, "1+2": 1.602, "4+5": 1.674, "7": 1.708, "8": 1.683, "9": 2.809, "End": 2.587}),
    ("Gold III", {"total": 1.7, "1+2": 1.511, "4+5": 1.554, "7": 1.643, "8": 1.543, "9": 2.457, "End": 2.397}),
    ("Emerald I", {"total": 1.587, "1+2": 1.43, "4+5": 1.45, "7": 1.58, "8": 1.429, "9": 2.168, "End": 2.116}),
    ("Emerald II", {"total": 1.49, "1+2": 1.359, "4+5": 1.361, "7": 1.519, "8": 1.338, "9": 1.932, "End": 1.783}),
    ("Emerald III", {"total": 1.408, "1+2": 1.296, "4+5": 1.286, "7": 1.46, "8": 1.265, "9": 1.737, "End": 1.48}),
    ("Diamond I", {"total": 1.323, "1+2": 1.228, "4+5": 1.209, "7": 1.389, "8": 1.193, "9": 1.543, "End": 1.224}),
    ("Diamond II", {"total": 1.241, "1+2": 1.16, "4+5": 1.14, "7": 1.308, "8": 1.128, "9": 1.365, "End": 1.08}),
    ("Diamond III", {"total": 1.168, "1+2": 1.096, "4+5": 1.081, "7": 1.218, "8": 1.076, "9": 1.214, "End": 1.022}),
    ("Netherite", {"total": 1.107, "1+2": 1.04, "4+5": 1.037, "7": 1.122, "8": 1.036, "9": 1.095, "End": 1.005}),
    ("Top 30", {"total": 1.045, "1+2": 0.983, "4+5": 0.993, "7": 1.008, "8": 0.995, "9": 0.993, "End": 0.994}),
]
# The parts ranked, by bucket. Buckets 3 and 6 aren't: they vary little with skill-level (from
# Iron to the top 30, less than the run-to-run noise). Ranked can't tell buckets 4 and 5 apart.
RANK_PARTS = {"1+2": (1, 2), "4+5": (4, 5), "7": (7,), "8": (8,), "9": (9,), "End": (10,)}
RANK_PART_NAMES = {"1+2": "Overworld", "4+5": "Bastion to fortress", "7": "First rod to blind",
                   "8": "Blind to stronghold", "9": "Stronghold to End", "End": "End"}
UNRANKED_BUCKETS = (3, 6)


def rank_for(ratio, key):
    """The best tier whose typical time / top-player time ("total" or a part) the run's matches or
    beats; "Coal" below Iron I."""
    best = "Coal"
    for name, ratios in RANKS:
        if ratio <= ratios[key]:
            best = name
    return best


def _num(text):
    try:
        return float(text) if text not in ("", None) else None
    except ValueError:
        return None


def _seconds(text):
    ms = parse_time(text) if text else None
    return None if ms is None else ms / 1000


def unscored_reason(row):
    """Why a run has no score, or None if it can be scored."""
    if row.get("result") != "finished":
        return "Only finished runs are scored."
    if not row.get("bucket_1"):
        return "This run's Hermes data hasn't loaded yet."
    final = _seconds(row.get("final_rta"))
    if final is None or any(_seconds(row.get(f"bucket_{i}")) is None for i in range(1, 10)):
        return "This run's times are incomplete."
    cheats = _seconds(row.get("cheats_from_rta"))
    if cheats is not None and cheats < final:  # opened to LAN before finishing (after is fine: /seed)
        return "This run was opened to LAN with cheats before it finished."
    if (row.get("last_structure") or "") not in OVERWORLD:  # imported before the seed type rule
        return "Rebuild from records (Settings) to score this run."
    return None


def score(row):
    """The run's score and how it was worked out, or None if it can't be scored (see
    unscored_reason)."""
    if unscored_reason(row):
        return None
    final = _seconds(row.get("final_rta"))
    t = {i: _seconds(row.get(f"bucket_{i}")) for i in range(1, 10)}
    end_time = max(0.0, final - sum(t.values()))
    explosives = _num(row.get("explosives"))
    hit = _num(row.get("one_cycle_hit"))
    multi = MULTI_CYCLE.get(int(explosives)) if explosives is not None and explosives <= 2 else None
    if multi:
        median, p90 = multi
        t[10] = min(end_time, median) + max(0.0, end_time - p90)
    else:
        t[10] = end_time if hit == 0 else min(end_time, C)  # a missed one cycle counts in full

    # ---- The run's inputs ----
    structure = row.get("last_structure") or ""
    w1, w2 = OVERWORLD[structure]
    w = {1: w1, 2: w2, **W}
    if multi:
        w[10] = multi[0]
    n = _num(row.get("fortress_to_stronghold"))
    d = {3: _num(row.get("to_first_structure")), 5: _num(row.get("bastion_to_fortress")),
         7: n, 8: None if n is None else n * 8}
    kills, rods = _num(row.get("blazes_killed")), _num(row.get("blaze_rods"))
    luck = None
    if kills is not None and rods is not None:
        luck = BLAZE_S * (max(0, kills - STRAYS) - max(0, 2 * rods - STRAYS))
    fire_res = _num(row.get("fire_resistance"))
    pearls = _num(row.get("ender_pearls"))
    iron_pick = _num(row.get("iron_pick"))

    # ---- Seed difficulty ----
    f = {i: 1.0 for i in range(1, 11)}
    openness = {i: _num(row.get(f"terrain_{i}")) for i in (3, 5, 7)}
    g = {i: TERRAIN[terrain_level(openness[i])] if openness[i] is not None else 1.0 for i in (3, 5, 7)}
    for i, (alpha, beta, d_bar) in FITS.items():
        distance = d[i]
        if distance is None:
            if i != 7 or luck is None:
                continue  # unknown distance (no ghost file, or the structures weren't in order)
            distance = d_bar  # drop luck still counts; the stronghold is taken as average
        extra = (luck or 0) if i == 7 else 0
        f[i] = max(0.0, (alpha + beta * distance * g.get(i, 1.0) + extra) / (alpha + beta * d_bar))
    ow = {1: _num(row.get("spawn_to_structure")), 2: _num(row.get("structure_to_portal"))}
    if structure in OVERWORLD_TRAVEL:
        beta, *ranges = OVERWORLD_TRAVEL[structure]
        for i, top in ((1, ranges[0]), (2, ranges[1])):
            if top is not None and ow[i] is not None and w[i] > 0:
                f[i] = max(0.0, (w[i] + beta * (ow[i] - top / 2)) / w[i])

    # ---- Resource shortages ----
    travel_short = min(18, max(0, COMFORTABLE_PEARLS - pearls)) if pearls is not None else 0
    zeta = 0.0 if pearls is None or pearls >= 3 or multi else (0.75 if pearls == 2 else 1.0)
    shortages = [
        ("Only 1 fire resistance potion", 1 if fire_res == 1 else 0, ONE_FIRE_RES),
        ("No fire resistance potions", 1 if fire_res == 0 else 0, NO_FIRE_RES),
        ("Only 3 or 4 explosives at End enter",
         1 if explosives is not None and 2 < explosives < EXPLOSIVES_NEEDED else 0, FEW_EXPLOSIVES),
        ("Travel pearls short", travel_short, PER_TRAVEL_PEARL),
        ("No iron pickaxe before the nether", 1 if iron_pick == 0 else 0, NO_IRON_PICK),
    ]

    buckets = []
    for i in range(1, 11):
        allowance = sum(gamma.get(i, 0) * x for _, x, gamma in shortages)
        expected = w[i] * f[i] + allowance
        if i == 10 and not multi:
            expected = min(C, expected + zeta * (C - w[10]))
        buckets.append({"bucket": i, "name": BUCKET_NAMES[i], "t": t[i], "W": w[i], "f": f[i],
                        "allowance": expected - w[i] * f[i], "expected": expected, "lost": t[i] - expected})
    total = sum(b["lost"] for b in buckets)
    # Each part's rank, and the most RTA (and lost) each tier would take on it on this seed.
    parts = []
    for key, numbers in RANK_PARTS.items():
        shown = sum(buckets[i - 1]["expected"] for i in numbers)  # the table's expected
        if key == "End":  # uncapped, like the Ranked samples: against W_10
            time, base = end_time, W[10]
        else:
            time, base = sum(t[i] for i in numbers), shown
        ratio = time / base
        parts.append({"part": key, "name": RANK_PART_NAMES[key], "buckets": list(numbers),
                      "ratio": ratio, "rank": rank_for(ratio, key),
                      "cutoffs": [{"rank": name, "ratio": r[key], "rta": r[key] * base,
                                   "lost": r[key] * base - shown} for name, r in RANKS]})
    # The run's time / the time a top player is expected to take on this seed with its resources.
    expected_total = sum(b["expected"] for b in buckets)
    total_ratio = sum(b["t"] for b in buckets) / expected_total
    return {
        "score": total,
        "ratio": total_ratio,
        "rank": rank_for(total_ratio, "total"),
        # The most RTA (the End counted as in the score) and score each tier would have on this seed.
        "cutoffs": [{"rank": name, "ratio": r["total"], "rta": r["total"] * expected_total,
                     "score": (r["total"] - 1) * expected_total} for name, r in RANKS],
        "parts": parts,
        "unranked_buckets": list(UNRANKED_BUCKETS),
        "buckets": buckets,
        "inputs": {
            "structure": structure, "structure_name": STRUCTURE_NAMES[structure], "d3": d[3], "d8": d[8],
            "d1": ow[1], "d2": ow[2], "ow_travel": OVERWORLD_TRAVEL.get(structure),
            "terrain": {str(i): {"open": openness[i], "level": terrain_level(openness[i]), "g": g[i]}
                        for i in (3, 5, 7)}, "d5": d[5], "n": d[7],
            "kills": kills, "rods": rods, "luck": luck, "fire_res": fire_res, "pearls": pearls,
            "travel_short": travel_short, "zeta": zeta, "explosives": explosives, "iron_pick": iron_pick,
            "final_rta": final, "end_time": end_time, "one_cycle_hit": hit,
            "multi_cycle": None if not multi else {"median": multi[0], "p90": multi[1]},
        },
        "shortages": [{"name": name, "x": x, "gamma": {str(k): v for k, v in gamma.items()}}
                      for name, x, gamma in shortages],
        "constants": {"C": C, "fits": {str(k): v for k, v in FITS.items()}, "blaze_s": BLAZE_S, "strays": STRAYS,
                      "comfortable_pearls": COMFORTABLE_PEARLS, "explosives_needed": EXPLOSIVES_NEEDED,
                      "multi_cycle": {str(k): v for k, v in MULTI_CYCLE.items()},
                      "terrain_cutoffs": TERRAIN_CUTOFFS, "terrain": TERRAIN},
    }
