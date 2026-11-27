import struct
import tempfile
import unittest
from pathlib import Path

from icy_rsg_tracker.phases import GHOST_RECORD, Ghost, PhaseTracker, is_block, raw_materials


class RawMaterialsTest(unittest.TestCase):
    def test_crafted_items_count_as_what_they_are_made_of(self):
        totals, parts = raw_materials({
            "0": ("minecraft:bucket", 1), "1": ("minecraft:iron_pickaxe", 1), "2": ("minecraft:oak_log", 2),
            "3": ("minecraft:stick", 3), "4": ("minecraft:gold_nugget", 9), "5": ("minecraft:dirt", 20),
            "6": ("minecraft:bread", 5), "7": ("minecraft:white_bed", 3), "8": ("minecraft:flint", 4),
            "9": ("minecraft:stone_axe", 1), "10": ("minecraft:diamond", 2),
        })
        self.assertEqual(totals, {"planks": 8 + 1.5 + 1 + 1, "other_blocks": 20, "iron": 6, "gold": 1,
                                  "diamonds": 2, "cobblestone": 3, "food": 5})
        self.assertEqual(parts["iron"], {"bucket": 1, "iron_pickaxe": 1})

    def test_blocks(self):
        for item in ("dirt", "oak_door", "netherrack", "soul_sand", "obsidian"):
            self.assertTrue(is_block(f"minecraft:{item}"), item)
        for item in ("ender_pearl", "iron_pickaxe", "water_bucket", "bread", "potion[fire_resistance]", "flint"):
            self.assertFalse(is_block(f"minecraft:{item}"), item)


class PhaseTest(unittest.TestCase):
    """Play logs built event by event: times are ms (real and in-game move together)."""

    def setUp(self):
        self.p = PhaseTracker()
        self.t = 1_000_000

    def at(self, ms):
        self.t += ms

    def send(self, kind, data):
        self.p.event({"time": self.t, "type": kind, "data": data,
                      "speedrunigt": {"igt": self.t - 999_000, "rta": self.t - 999_000}})

    def structures(self, *names):
        self.send("inside_structures", {"structures": [f"minecraft:{n}" for n in names]})

    def stat(self, stat, diff=1):
        self.send("stat", {"stat": stat, "value": 0, "diff": diff})

    def dimension(self, old, new, old_pos=None, pos=None):
        self.send("dimension", {"old_dimension": f"minecraft:{old}", "dimension": f"minecraft:{new}",
                                "old_position": old_pos, "position": pos})

    def chest(self):
        self.send("screen", {"title": {"translate": "container.chest"}, "is_pause": False})
        self.at(500)
        self.send("screen", {"title": None, "is_pause": False})

    def inv(self, **slots):
        self.send("inventory_slots", {"slots": {k[1:]: v and {"id": f"minecraft:{v[0]}", "Count": v[1]}
                                                 for k, v in slots.items()}})

    def test_overworld(self):
        self.chest()                                        # the chest is opened just before Hermes notices
        self.at(1000); self.structures("buried_treasure")
        self.at(2000); self.structures()
        self.at(5000); self.structures("village")           # walked through, no chest
        self.at(5000); self.structures()
        self.at(5000); self.structures("ocean_ruin")        # doesn't count as the last structure
        self.at(5000); self.structures()
        self.inv(s0=("bucket", 1), s1=("oak_planks", 10))
        self.at(20_000); self.dimension("overworld", "the_nether")
        ow = self.p.summary(None)["overworld"]
        self.assertEqual([(s["structure"], s["looted"]) for s in ow["structures"]],
                         [("buried_treasure", True), ("village", False), ("ocean_ruin", False)])
        self.assertEqual(ow["to_nether"], {"structure": "village", "ms": 30_000, "distance": None})  # no ghost
        self.assertEqual((ow["materials"]["iron"], ow["materials"]["planks"]), (3, 10))

    def test_nether(self):
        self.inv(s0=("netherrack", 20), s1=("gold_ingot", 30))
        self.dimension("overworld", "the_nether")
        self.at(1000); self.stat("minecraft.used:minecraft.netherrack", 6); self.stat("minecraft.used:minecraft.ender_pearl")
        self.at(9000); self.structures("bastion_remnant")
        self.at(1000); self.stat("minecraft.used:minecraft.netherrack", 3)  # in the bastion: not counted
        self.at(20_000); self.structures()
        self.at(10_000); self.structures("bastion_remnant")  # back in for a moment: still one visit
        self.at(10_000); self.structures()
        self.at(60_000); self.structures("bastion_remnant")  # a minute later: another visit
        self.at(5_000); self.structures()
        self.at(20_000); self.structures("fortress")
        self.at(30_000); self.stat("minecraft.picked_up:minecraft.blaze_rod")
        self.at(40_000); self.stat("minecraft.picked_up:minecraft.blaze_rod")
        ne = self.p.summary(None)["nether"]
        self.assertEqual(ne["to_structure"]["structure"], "bastion_remnant")
        self.assertEqual((ne["to_structure"]["ms"], ne["to_structure"]["blocks"]), (10_000, 6))
        self.assertEqual(ne["first_rod_ms"], 30_000)
        columns = self.p.summary(None)["columns"]
        self.assertEqual((columns["bastion_time"], columns["first_to_last_rod"]), (41_000 + 5_000, 40_000))
        self.assertEqual(ne["fortress_slots"], {"0": ["netherrack", 20], "1": ["gold_ingot", 30]})

    def test_blind_and_stronghold(self):
        self.dimension("overworld", "the_nether")
        self.at(60_000); self.dimension("the_nether", "overworld", {"x": 100, "y": 60, "z": 0}, {"x": 800, "y": 60, "z": 0})
        self.at(20_000); self.dimension("overworld", "the_nether")  # back in, to a portal nearer the stronghold
        self.at(30_000); self.dimension("the_nether", "overworld", {"x": 130, "y": 90, "z": 40}, {"x": 1040, "y": 60, "z": 320})
        self.at(60_000); self.structures("stronghold")
        self.stat("minecraft.used:minecraft.ender_eye")            # thrown, picked back up
        self.at(3000); self.stat("minecraft.picked_up:minecraft.ender_eye")
        self.at(9000); self.stat("minecraft.used:minecraft.ender_eye", 9)
        self.at(2000); self.dimension("overworld", "the_end", {"x": 800, "y": 30, "z": 300}, {"x": 100, "y": 50, "z": 0})
        s = self.p.summary(None)
        self.assertEqual(s["stronghold"], {"eyes_placed": 9})
        blind = s["nether"]["blind"]
        self.assertEqual((blind["nether_distance"], blind["distance"]), (50, 400))  # y doesn't count

    def test_blind_portal_used_to_the_stronghold(self):
        self.dimension("overworld", "the_nether")
        self.at(60_000); self.dimension("the_nether", "overworld", {"x": 100, "y": 60, "z": 0}, {"x": 800, "y": 60, "z": 0})
        self.at(60_000); self.structures("stronghold")
        self.assertEqual(self.p.summary(None)["nether"]["blind"]["distance"], 0)

    def test_seed_type_is_the_last_looted_structure_of_the_five(self):
        self.stat("minecraft.custom:minecraft.jump")        # the run's first event, at 1 s
        self.at(1000); self.chest(); self.at(1000); self.structures("village")
        self.at(9000); self.structures()                    # left the village at 12.5 s
        self.at(5000); self.chest(); self.structures("mineshaft")
        self.at(5000); self.structures()                    # a mineshaft: not one of the five
        self.at(4000); self.structures("shipwreck")         # walked through, nothing looted
        self.at(4000); self.structures()
        self.at(10_000); self.dimension("overworld", "the_nether")
        c = self.p.summary(None)["columns"]
        self.assertEqual((c["last_structure"], c["bucket_1"]), ("village", 12_500))
        self.assertEqual(c["bucket_1"] + c["bucket_2"], 41_000 - 1000)  # everything before the nether

    def test_one_cycle_hit(self):
        for wait, hit in ((12_000, 1), (150_000, 0)):
            self.setUp()
            self.stat("minecraft.custom:minecraft.jump")
            self.at(60_000); self.dimension("overworld", "the_nether")
            self.at(60_000); self.dimension("overworld", "the_end")
            self.at(200_000); self.stat("minecraft.used:minecraft.white_bed", 4)  # a late perch: fine
            self.at(wait); self.stat("minecraft.killed:minecraft.ender_dragon")
            self.assertEqual(self.p.summary(None)["columns"]["one_cycle_hit"], hit)

    def test_structureless(self):
        self.stat("minecraft.custom:minecraft.jump")
        self.at(30_000); self.dimension("overworld", "the_nether")
        c = self.p.summary(None)["columns"]
        self.assertEqual((c["last_structure"], c["bucket_1"], c["bucket_2"]), ("", 0, 30_000))

    def test_nothing_after_lan(self):
        self.send("game_info", {"open_to_lan": True, "cheats_allowed": True})
        self.dimension("overworld", "the_nether")
        self.assertEqual(self.p.summary(None)["nether"], {})


def write_ghost(folder, ticks):
    """ticks: [(time ms, x, z)]."""
    ghosts = Path(folder) / "ghosts"
    ghosts.mkdir(exist_ok=True)
    data = b"".join(GHOST_RECORD.pack(t, x, 64.0, z, 0.0, 0.0, 20.0, 0, 0x20) for t, x, z in ticks)
    (ghosts / "player.ghost").write_bytes(data)
    return data


class GhostTest(unittest.TestCase):
    def test_positions(self):
        with tempfile.TemporaryDirectory() as d:
            data = write_ghost(d, [(1000 + 50 * i, 3.0 * i, 4.0 * i) for i in range(11)])
            ghost = Ghost.read(Path(d), 1000)
            self.assertEqual(ghost.position(1120), {"x": 6.0, "z": 8.0})  # the tick at or before
            self.assertIsNone(ghost.position(900))                        # before the ghost starts
            self.assertIsNone(ghost.position(9000))                       # long after it ends
            (Path(d) / "ghosts" / "player.ghost").write_bytes(data[:-3])  # not whole records: not read
            self.assertIsNone(Ghost.read(Path(d), 1000))

    def test_straight_line_distances(self):
        p = PhaseTracker()
        t = [1_000_000]

        def send(kind, data, ms=0):
            t[0] += ms
            p.event({"time": t[0], "type": kind, "data": data, "speedrunigt": {"igt": t[0] - 999_000}})

        send("dimension", {"old_dimension": None, "dimension": "minecraft:overworld", "position": {"x": 0, "y": 70, "z": 0}})
        send("inside_structures", {"structures": ["minecraft:shipwreck"]}, 10_000)       # at 300, 400
        send("inside_structures", {"structures": []}, 10_000)                             # left at 300, 420
        send("inside_structures", {"structures": ["minecraft:village"]}, 10_000)         # at 300, 1000
        send("inside_structures", {"structures": []}, 10_000)                             # left at 300, 1040
        send("dimension", {"old_dimension": "minecraft:overworld", "dimension": "minecraft:the_nether",
                           "old_position": {"x": 300, "y": 60, "z": 1100}, "position": {"x": 37, "y": 60, "z": 137}}, 10_000)
        send("inside_structures", {"structures": ["minecraft:bastion_remnant"]}, 30_000)  # at 37, 237
        where = {1_010_000: (300, 400), 1_020_000: (300, 420), 1_030_000: (300, 1000), 1_040_000: (300, 1040),
                 1_080_000: (37, 237)}
        with tempfile.TemporaryDirectory() as d:
            write_ghost(d, [(time, x, z) for time, (x, z) in sorted(where.items())])
            s = p.summary(Ghost.read(Path(d), 1_000_000))
        self.assertEqual(s["columns"]["spawn_to_structures"], 500 + 600)
        self.assertEqual(s["overworld"]["to_nether"]["distance"], 60)
        self.assertEqual(s["columns"]["to_first_structure"], 100)


if __name__ == "__main__":
    unittest.main()
