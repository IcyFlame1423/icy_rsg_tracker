import unittest

from icy_rsg_tracker.hermes import DESPAWN_MS, ItemCounter


class ItemCountTest(unittest.TestCase):
    """Play logs built event by event; times are ms."""

    def setUp(self):
        self.c = ItemCounter()
        self.t = 1_000_000  # real time
        self.igt = 1000     # in-game time

    def at(self, ms, igt=True):
        """ms later; in-game time moves with it unless the world was closed (igt=False)."""
        self.t += ms
        if igt:
            self.igt += ms

    def send(self, kind, data):
        self.c.event({"time": self.t, "type": kind, "data": data, "speedrunigt": {"igt": self.igt}})

    def inv(self, **slots):
        """inv(s0=("ender_pearl", 3), s1=None): set slots 0 and 1."""
        data = {}
        for name, value in slots.items():
            if value is None:
                data[name[1:]] = None
            else:
                item, count, *tag = value
                data[name[1:]] = {"id": f"minecraft:{item}", "Count": count, **({"tag": tag[0]} if tag else {})}
        self.send("inventory_slots", {"slots": data})

    def stat(self, stat, diff=1):
        self.send("stat", {"stat": stat, "value": 0, "diff": diff})

    def screen(self, title=None, pause=False):
        data = {} if title is None else {"title": {"translate": title}, "is_pause": pause}
        if title is None:
            data = {"title": None, "is_pause": False}
        self.send("screen", data)

    def dimension(self, dim):
        self.send("dimension", {"dimension": f"minecraft:{dim}"})

    def got(self, item):
        return self.c.obtained[item]

    def test_pickups_and_moving_items_in_a_menu(self):
        self.inv(s0=("ender_pearl", 5))
        self.at(1000); self.inv(s0=("ender_pearl", 9))
        self.at(1000); self.screen("container.crafting")
        self.at(300); self.inv(s0=None)                     # picked up with the cursor
        self.at(300); self.inv(s5=("ender_pearl", 9))       # put down elsewhere
        self.at(300); self.screen(None)
        self.assertEqual(self.got("ender_pearls"), 9)

    def test_pearls_are_the_most_held_at_once(self):
        self.inv(s0=("ender_pearl", 4))
        self.at(1000); self.stat("minecraft.used:minecraft.ender_pearl"); self.inv(s0=("ender_pearl", 3))
        self.at(1000); self.inv(s0=("ender_pearl", 5))      # 2 more traded
        self.at(1000); self.stat("minecraft.custom:minecraft.deaths"); self.inv(s0=None)
        self.at(5000); self.inv(s0=("ender_pearl", 5))      # picked back up
        self.assertEqual(self.got("ender_pearls"), 5)

    def test_crafting_eyes_and_closing_the_screen(self):
        # Pearls left in the crafting grid come back as the screen closes: not new.
        self.inv(s0=("blaze_rod", 3), s1=("obsidian", 4))
        self.at(1000); self.screen("container.crafting")
        self.at(300); self.inv(s0=None, s1=None)            # into the grid
        self.at(300); self.screen(None)
        self.at(5); self.inv(s0=("blaze_rod", 3), s1=("obsidian", 4))
        self.assertEqual((self.got("blaze_rods"), self.got("obsidian")), (3, 4))

    def test_death_and_picking_items_back_up(self):
        self.inv(s0=("ender_pearl", 10), s1=("blaze_rod", 4))
        self.at(1000); self.stat("minecraft.custom:minecraft.deaths"); self.at(2); self.inv(s0=None, s1=None)
        self.at(20_000); self.inv(s3=("ender_pearl", 10), s4=("blaze_rod", 4))  # picked back up
        self.at(1000); self.inv(s4=("blaze_rod", 6))                            # 2 new
        self.assertEqual((self.got("ender_pearls"), self.got("blaze_rods")), (10, 6))

    def test_items_despawn_after_five_minutes(self):
        self.inv(s0=("blaze_rod", 10))
        self.stat("minecraft.custom:minecraft.deaths"); self.inv(s0=None)
        self.at(DESPAWN_MS + 1000); self.inv(s0=("blaze_rod", 3))  # can't be the dropped ones
        self.assertEqual(self.got("blaze_rods"), 13)

    def test_leaving_the_world_and_coming_back(self):
        # Items don't despawn while the world is closed: picking them up later isn't new.
        self.inv(s0=("blaze_rod", 10))
        self.stat("minecraft.custom:minecraft.deaths"); self.inv(s0=None)
        self.at(60 * 60 * 1000, igt=False)  # an hour later, the world is opened again
        self.at(30_000); self.inv(s0=("blaze_rod", 10))
        self.assertEqual(self.got("blaze_rods"), 10)

    def test_thrown_out_and_picked_up_again(self):
        self.inv(s0=("white_bed", 3))
        self.at(1000); self.stat("minecraft.dropped:minecraft.white_bed", 3); self.inv(s0=None)
        self.at(3000); self.inv(s2=("white_bed", 3))
        self.assertEqual(self.got("beds"), 3)

    def test_chests(self):
        self.screen("container.chest")
        self.at(500); self.inv(s0=("obsidian", 4), s1=("blaze_rod", 2))  # loot
        self.at(500); self.inv(s0=None)                                 # put back
        self.at(500); self.inv(s0=("obsidian", 4))                      # taken again
        self.screen(None)
        # Obsidian from a chest counts; blaze rods only count from blazes.
        self.assertEqual((self.got("obsidian"), self.got("blaze_rods")), (4, 0))

    def test_beds(self):
        self.screen("container.crafting")
        self.at(500); self.inv(s0=("white_bed", 1))                   # crafted
        self.at(500); self.inv(s0=("white_bed", 2))
        self.screen(None)
        # Placed for a death reset in the overworld, then broken and picked up again.
        self.at(1000); self.stat("minecraft.used:minecraft.white_bed"); self.inv(s0=("white_bed", 1))
        self.at(9000); self.stat("minecraft.mined:minecraft.white_bed")
        self.at(500); self.inv(s0=("white_bed", 2))
        # Blown up in the nether: gone.
        self.dimension("the_nether")
        self.at(1000); self.stat("minecraft.used:minecraft.white_bed"); self.inv(s0=("white_bed", 1))
        self.at(1000); self.stat("minecraft.mined:minecraft.white_bed"); self.inv(s0=("white_bed", 2))  # found one
        self.assertEqual(self.got("beds"), 3)

    def test_nothing_counts_after_opening_to_lan(self):
        self.inv(s0=("ender_pearl", 4))
        self.at(1000); self.send("game_info", {"open_to_lan": False, "cheats_allowed": False})
        self.at(1000); self.inv(s0=("ender_pearl", 6))
        self.at(1000); self.send("game_info", {"open_to_lan": True, "cheats_allowed": True})
        self.at(1000); self.inv(s0=("ender_pearl", 16), s1=("blaze_rod", 64))  # e.g. /give
        self.assertEqual((self.got("ender_pearls"), self.got("blaze_rods")), (6, 0))

    def structures(self, *names):
        self.send("inside_structures", {"structures": [f"minecraft:{n}" for n in names]})

    def detail(self, name):
        return self.c.details()[name]

    def test_blazes_pearls_and_potions(self):
        self.stat("minecraft.killed:minecraft.blaze", 3)
        self.inv(s0=("ender_pearl", 10), s1=("potion", 2, {"Potion": "minecraft:fire_resistance"}))
        self.at(1000); self.stat("minecraft.used:minecraft.ender_pearl"); self.inv(s0=("ender_pearl", 9))
        self.at(1000); self.stat("minecraft.used:minecraft.potion"); self.inv(s1=("potion", 1, {"Potion": "minecraft:fire_resistance"}))
        self.at(1000); self.stat("minecraft.crafted:minecraft.ender_eye", 6)
        self.dimension("the_end")
        self.at(1000); self.stat("minecraft.used:minecraft.ender_pearl")  # in the End: not counted
        self.assertEqual([self.detail(n) for n in ("blazes_killed", "pearls_used", "pearls_into_eyes", "fire_resistance_used")],
                         [3, 1, 6, 1])

    def test_where_beds_went(self):
        self.inv(s0=("white_bed", 9))
        bed = lambda: self.stat("minecraft.used:minecraft.white_bed")
        bed()                                                     # overworld, broken again below
        self.at(5000); self.stat("minecraft.mined:minecraft.white_bed")
        self.at(1000); bed()                                      # overworld, never broken: lost
        self.dimension("the_nether")
        self.at(1000); bed(); self.at(1000); bed()                # nether
        self.structures("fortress")
        self.at(1000); bed()                                      # fortress
        self.dimension("the_end")
        self.at(1000); bed(); self.at(1000); bed()                # End
        self.assertEqual([self.detail(n) for n in ("beds_nether", "beds_fortress", "beds_end", "beds_lost")],
                         [2, 1, 2, 1])

    def test_beds_dropped_and_never_picked_up_are_lost(self):
        self.inv(s0=("white_bed", 3))
        self.at(1000); self.stat("minecraft.custom:minecraft.deaths"); self.inv(s0=None)
        self.assertEqual(self.detail("beds_lost"), 3)

    def test_where_anchors_went(self):
        self.inv(s0=("respawn_anchor", 4))
        anchor = lambda: self.stat("minecraft.used:minecraft.respawn_anchor")
        anchor()                                                  # overworld: blown up, lost
        self.dimension("the_nether")
        self.at(1000); anchor()                                   # nether, mined again below
        self.at(5000); self.stat("minecraft.mined:minecraft.respawn_anchor")
        self.dimension("the_end")
        self.at(1000); anchor()
        self.assertEqual((self.detail("anchors_end"), self.detail("anchors_lost")), (1, 1))

    def test_obsidian_is_the_most_held_and_from_bastions_and_the_diamond_pickaxe(self):
        self.inv(s0=("obsidian", 3))
        self.structures("bastion_remnant")
        self.at(1000); self.inv(s0=("obsidian", 10))
        self.structures()
        self.at(1000); self.stat("minecraft.used:minecraft.obsidian", 4); self.inv(s0=("obsidian", 6))
        self.at(1000); self.inv(s0=("obsidian", 8))
        self.assertEqual((self.got("obsidian"), self.detail("obsidian_bastion")), (10, 7))
        self.assertEqual(self.detail("diamond_pickaxe"), 0)
        self.at(1000); self.inv(s5=("diamond_pickaxe", 1, {"Damage": 0}))
        self.assertEqual(self.detail("diamond_pickaxe"), 1)

    def test_only_fire_resistance_potions(self):
        self.inv(s0=("potion", 1, {"Potion": "minecraft:fire_resistance"}),
                 s1=("splash_potion", 1, {"Potion": "minecraft:long_fire_resistance"}),
                 s2=("potion", 1, {"Potion": "minecraft:water"}))
        self.assertEqual(self.got("fire_resistance"), 2)


if __name__ == "__main__":
    unittest.main()
