import unittest

from icy_rsg_tracker import model


def row(**changes):
    """A finished run that's exactly a top player's median on an average seed."""
    r = {
        "result": "finished", "cheats_from_rta": "", "last_structure": "shipwreck",
        "to_first_structure": "112", "bastion_to_fortress": "128", "fortress_to_stronghold": "168.125", "spawn_to_structure": "32", "structure_to_portal": "80",
        "blazes_killed": "12", "blaze_rods": "6", "fire_resistance": "3", "ender_pearls": "24",
        "explosives": "6", "iron_pick": "1",
    }
    w = {1: model.OVERWORLD["shipwreck"][0], 2: model.OVERWORLD["shipwreck"][1], **model.W}
    for i in range(1, 10):
        r[f"bucket_{i}"] = f"{int(w[i] // 60)}:{w[i] % 60:06.3f}"
    total = sum(w[i] for i in range(1, 11))
    r["final_rta"] = f"{int(total // 60)}:{total % 60:06.3f}"
    r.update(changes)
    return r


class ScoreTest(unittest.TestCase):
    def test_a_top_players_median_run_scores_zero(self):
        self.assertAlmostEqual(model.score(row())["score"], 0, places=1)

    def test_seconds_lost_add_up(self):
        base = row()
        m, s = base["final_rta"].split(":")
        slower = float(m) * 60 + float(s) + 20
        # 20 s slower from blind to stronghold (1:32.7 -> 1:52.7), so the run ends 20 s later.
        sc = model.score(row(bucket_8="1:52.700", final_rta=f"{int(slower // 60)}:{slower % 60:06.3f}"))
        self.assertAlmostEqual(sc["score"], 20, places=1)
        self.assertAlmostEqual(sc["buckets"][7]["lost"], 20, places=1)

    def test_a_far_bastion_is_allowed_for(self):
        near, far = model.score(row(to_first_structure="20")), model.score(row(to_first_structure="220"))
        self.assertLess(far["buckets"][2]["expected"], 100)
        self.assertGreater(far["buckets"][2]["expected"], near["buckets"][2]["expected"])
        self.assertLess(far["score"], near["score"])  # same time, harder seed: a better score

    def test_ranks(self):
        top30, netherite = model.RANKS[-1][1], model.RANKS[-2][1]
        self.assertEqual(model.rank_for(top30["total"], "total"), "Top 30")
        self.assertEqual(model.rank_for(netherite["total"], "total"), "Netherite")
        self.assertEqual(model.rank_for(netherite["total"] + 0.01, "total"), "Diamond III")
        self.assertEqual(model.rank_for(model.RANKS[0][1]["total"] + 0.01, "total"), "Coal")
        self.assertEqual(model.rank_for(1.0, "8"), "Netherite")    # 1.0x: between top 30 and Netherite
        for key in ("total", *model.RANK_PARTS):                   # every level better than the one before
            values = [ratios[key] for _, ratios in model.RANKS]
            self.assertEqual(values, sorted(values, reverse=True), key)

    def test_a_tier_takes_longer_on_a_longer_seed(self):
        """Every bucket 1.45x what a top player is expected to take (between Emerald II's 1.49 and
        Emerald III's 1.41) is Emerald II on an average seed and on a far stronghold alike: a
        tier's time scales with the seed instead of adding fixed seconds."""
        ranks = []
        for far in ("168.125", "300"):
            expected = {b["bucket"]: b["expected"] for b in model.score(row(fortress_to_stronghold=far))["buckets"]}
            t = {i: expected[i] * 1.45 for i in expected}
            clock = lambda s: f"{int(s // 60)}:{s % 60:06.3f}"
            r = row(fortress_to_stronghold=far, final_rta=clock(sum(t.values())),
                    **{f"bucket_{i}": clock(t[i]) for i in range(1, 10)})
            ranks.append(model.score(r)["rank"])
        self.assertEqual(ranks, ["Emerald II", "Emerald II"])

    def test_a_run_at_top_player_times_ranks_top_30(self):
        sc = model.score(row())
        self.assertIn(sc["rank"], ("Top 30", "Netherite"))  # 1.0x: just under the top 30's 1.045 median
        for part in sc["parts"]:  # exactly a top player's time: 1.0x, between the two
            self.assertIn(part["rank"], ("Top 30", "Netherite"), part["name"])
        self.assertEqual(sc["unranked_buckets"], [3, 6])

    def test_overworld_distance_at_a_travel_speed(self):
        far = model.score(row(spawn_to_structure="64", structure_to_portal="160"))["buckets"]
        self.assertAlmostEqual(far[0]["expected"] - model.OVERWORLD["shipwreck"][0], 0.15 * 32, places=2)   # shipwreck: 0.15 s/block
        self.assertAlmostEqual(far[1]["expected"] - model.OVERWORLD["shipwreck"][1], 0.15 * 80, places=2)
        rp = model.score(row(last_structure="ruined_portal", spawn_to_structure="0", structure_to_portal="300"))
        self.assertAlmostEqual(rp["buckets"][0]["expected"], model.OVERWORLD["ruined_portal"][0] - 0.2 * 24, places=2)
        self.assertAlmostEqual(rp["buckets"][1]["f"], 1.0)  # the portal is the structure

    def test_a_far_stronghold_is_allowed_for(self):
        near, far = (model.score(row(fortress_to_stronghold=str(n)))["buckets"] for n in (60, 250))
        self.assertLess(near[7]["expected"], model.W[8])
        self.assertGreater(far[7]["expected"], model.W[8])
        self.assertGreater(far[6]["expected"], near[6]["expected"])

    def test_terrain_scales_the_time_per_block(self):
        b = {lvl: model.score(row(terrain_3=str(o)))["buckets"][2]
             for lvl, o in (("poor", 20), ("average", 40), ("good", 80))}
        alpha, beta, _ = model.FITS[3]
        for lvl, bucket in b.items():
            f = (alpha + beta * 112 * model.TERRAIN[lvl]) / (alpha + beta * 112)  # an average distance
            self.assertAlmostEqual(bucket["expected"], model.W[3] * f, places=2)
        self.assertEqual(model.score(row())["buckets"][2]["f"], 1.0)  # no terrain known: as before

    def test_shortages_raise_the_expected_time(self):
        base = model.score(row())
        short = model.score(row(iron_pick="0", fire_resistance="0", ender_pearls="18"))
        self.assertAlmostEqual(base["score"] - short["score"], 19.8 + 30 + 3 * 10, places=1)

    def end(self, seconds, **changes):
        """The End bucket of a run that spends `seconds` in the End."""
        base = row(**changes)
        m, s = base["final_rta"].split(":")
        final = float(m) * 60 + float(s) - model.W[10] + seconds
        return model.score(row(final_rta=f"{int(final // 60)}:{final % 60:06.3f}", **changes))["buckets"][9]

    def test_a_one_cycle_that_hits_is_capped(self):
        b = self.end(300, explosives="4", one_cycle_hit="1")
        self.assertEqual((b["t"], b["expected"]), (model.C, model.C))  # a bad perch costs nothing
        b = self.end(300, explosives="10", ender_pearls="1", one_cycle_hit="1")
        self.assertEqual(b["expected"], model.C)                     # no pearls: no zero cycle

    def test_a_missed_one_cycle_counts_in_full(self):
        b = self.end(300, explosives="4", one_cycle_hit="0")
        self.assertAlmostEqual(b["t"], 300, places=1)
        self.assertAlmostEqual(b["lost"], 300 - model.C, places=1)

    def test_two_explosives_or_fewer_expect_more_perches(self):
        for explosives, (median, p90) in model.MULTI_CYCLE.items():
            lucky, unlucky, failed = (self.end(t, explosives=str(explosives)) for t in (median - 30, p90 - 5, p90 + 60))
            self.assertAlmostEqual(lucky["lost"], -30, places=1)    # faster than the median: a gain
            self.assertAlmostEqual(unlucky["lost"], 0, places=1)    # bad luck up to the 90th percentile: free
            self.assertAlmostEqual(failed["lost"], 60, places=1)    # past it: counted again

    def test_only_finished_runs_without_cheats_before_the_end(self):
        self.assertIsNone(model.score(row(result="reset")))
        self.assertIsNone(model.score(row(cheats_from_rta="5:00.000")))
        final = row()["final_rta"]
        self.assertIsNotNone(model.score(row(cheats_from_rta=final)))  # /seed after finishing

    def test_structureless_runs_get_their_own_overworld_time(self):
        sc = model.score(row(last_structure=""))
        self.assertEqual((sc["buckets"][0]["W"], sc["buckets"][1]["W"]), (0.0, 179.0))
        self.assertIsNone(model.score(row(last_structure="mineshaft")))  # an old row: rebuild


if __name__ == "__main__":
    unittest.main()
