import csv
import gzip
import json
import os
import re
import tempfile
import time
import unittest
from pathlib import Path

from icy_rsg_tracker import deaths, runs_csv
from icy_rsg_tracker.config import Config, Instance
from icy_rsg_tracker.importer import (CHEATS_AT_START, OTHER_INSTANCE, SET_SEED,
                                   import_records)
from icy_rsg_tracker.records import parse_record, parse_world_number
from icy_rsg_tracker.timefmt import format_ms, parse_time
from icy_rsg_tracker import watch as watch_mod
from unittest import mock

# date = ms timestamp when the run ended
T0 = 1_795_550_000_000


def make_record(world, date, rta, timelines=(), advancements=None, completed=False,
                run_type="random_seed", cheats=False, open_lan=None):
    return {
        "run_type": run_type, "is_completed": completed, "world_name": world,
        "is_cheat_allowed": cheats, "open_lan": open_lan,
        "date": date, "final_igt": rta - 10, "final_rta": rta,
        "timelines": [{"name": n, "igt": igt, "rta": igt + 5} for n, igt in timelines],
        "advancements": advancements or {},
    }


def adv(igt, complete=True, is_advancement=True):
    return {"complete": complete, "is_advancement": is_advancement, "igt": igt, "rta": igt + 5}


class TimeFormatTest(unittest.TestCase):
    def test_round_trip(self):
        for ms in (0, 999, 61_005, 1_492_560, 12_345_678):
            self.assertEqual(parse_time(format_ms(ms)), ms)
        self.assertEqual(format_ms(1_492_560), "24:52.560")
        self.assertEqual(format_ms(None), "")
        self.assertIsNone(parse_time(""))


class ParseRecordTest(unittest.TestCase):
    def test_home_portal_blind(self):
        # Left the nether by the home portal: SpeedRunIGT only fills in the blind on
        # reaching the stronghold, so the blind is when the nether was left.
        rec = make_record("Random Speedrun #1", T0, 900_000, timelines=[
            ("enter_nether", 144_146), ("nether_travel", 676_951), ("nether_travel_home", 676_951),
            ("nether_travel_blind", 830_507), ("enter_stronghold", 830_507)])
        run = parse_record(rec, "x")
        self.assertEqual((run.splits["blind"], run.splits["stronghold"]), (676_951, 830_507))
        # Home, back to the nether, then a real blind later: SpeedRunIGT's blind stands.
        rec = make_record("Random Speedrun #1", T0, 900_000, timelines=[
            ("nether_travel", 300_000), ("nether_travel_home", 300_000),
            ("nether_travel_blind", 700_000), ("enter_stronghold", 830_507)])
        self.assertEqual(parse_record(rec, "x").splits["blind"], 700_000)

    def test_splits_and_advancements(self):
        rec = make_record(
            "Random Speedrun #1926", T0, 1_500_000, completed=True,
            timelines=[("found_villager", 10), ("enter_nether", 292_994),
                       ("nether_travel", 984_341), ("nether_travel_blind", 984_341),
                       ("enter_end", 1_260_036)],
            advancements={
                "minecraft:story/iron_tools": adv(49_194),
                "minecraft:adventure/adventuring_time": adv(0, complete=False),
                "minecraft:recipes/misc/foo": adv(5, is_advancement=False),
            },
        )
        run = parse_record(rec, "abc")
        self.assertEqual(run.world_number, 1926)
        self.assertEqual(run.splits, {"nether": 292_994, "blind": 984_341, "end": 1_260_036})
        self.assertEqual(run.advancements, {"story/iron_tools": 49_194})
        self.assertTrue(run.completed)
        self.assertIsNone(run.cheats_from_rta)
        self.assertFalse(run.cheats_at_start)

    def test_lan_cheats_drop_later_splits(self):
        rec = make_record(
            "Random Speedrun #5", T0, 400_000, cheats=True, open_lan=300_000,
            timelines=[("enter_nether", 200_000), ("enter_bastion", 350_000)],
            advancements={"minecraft:story/iron_tools": adv(100_000),
                          "minecraft:nether/find_bastion": adv(350_000)},
        )
        run = parse_record(rec, "x")
        self.assertEqual(run.cheats_from_rta, 300_000)
        self.assertFalse(run.cheats_at_start)
        self.assertEqual(run.splits, {"nether": 200_000})
        self.assertEqual(run.advancements, {"story/iron_tools": 100_000})

    def test_lan_without_cheats_keeps_everything(self):
        rec = make_record("Random Speedrun #5", T0, 400_000, open_lan=100,
                          timelines=[("enter_nether", 200_000)])
        run = parse_record(rec, "x")
        self.assertIsNone(run.cheats_from_rta)
        self.assertEqual(run.splits, {"nether": 200_000})

    def test_cheats_at_start(self):
        run = parse_record(make_record("New World", T0, 1000, cheats=True), "x")
        self.assertTrue(run.cheats_at_start)

    def test_world_number(self):
        self.assertEqual(parse_world_number("Random Speedrun #24609"), 24609)
        self.assertIsNone(parse_world_number("New World (3)"))


class ImportTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.cfg = Config(speedrunigt_dir=root / "speedrunigt", output_dir=root / "data",
                          session_gap_minutes=30)
        self.cfg.records_dir.mkdir(parents=True)
        self.speedrun = self.cfg.instances[0]

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, run_id, record):
        (self.cfg.records_dir / f"{run_id}.json").write_text(json.dumps(record))

    def rows(self, instance=None):
        return runs_csv.load_rows(self.cfg.runs_csv(instance or self.speedrun))

    def test_import_sessions_worlds_generated_and_dedup(self):
        self.write("a", make_record("Random Speedrun #10", T0, 60_000))
        self.write("b", make_record("Random Speedrun #14", T0 + 120_000, 60_000))   # counter +4
        self.write("b2", make_record("Random Speedrun #12", T0 + 200_000, 60_000))  # out of order
        # Starts 2h after b2 ended -> new session
        self.write("c", make_record("Random Speedrun #15", T0 + 2 * 3_600_000, 60_000))
        self.write("s", make_record("Random Speedrun #16", T0, 1000, run_type="set_seed"))

        result = import_records(self.cfg)
        self.assertEqual(result.instances["speedrun"].added, 4)
        self.assertEqual(result.ignored, {SET_SEED: 1})

        rows = self.rows()
        self.assertEqual([r["run_id"] for r in rows], ["a", "b", "b2", "c"])
        self.assertEqual([r["session_id"] for r in rows], ["1", "1", "1", "2"])
        # Worlds #10..#15 = 6 generated, 4 played -> 2 wall resets (#11, #13)
        self.assertEqual([r["worlds_generated"] for r in rows], ["1", "4", "0", "1"])

        # Unchanged records aren't read again.
        r = import_records(self.cfg).instances["speedrun"]
        self.assertEqual((r.added, r.updated, r.total), (0, 0, 4))

    def test_records_split_by_instance(self):
        self.cfg.instances.append(Instance("ranked", re.compile(r"^New World")))
        ranked = self.cfg.instances[1]
        self.write("a", make_record("Random Speedrun #1", T0, 1000))
        self.write("b", make_record("New World (3)", T0, 1000))
        self.write("c", make_record("mcsrranked #abc", T0, 1000))     # no instance
        self.write("d", make_record("New World (4)", T0, 1000, cheats=True))  # cheats from start

        result = import_records(self.cfg)
        self.assertEqual([r["run_id"] for r in self.rows()], ["a"])
        self.assertEqual([r["run_id"] for r in self.rows(ranked)], ["b"])
        self.assertEqual(result.ignored, {OTHER_INSTANCE: 1, CHEATS_AT_START: 1})

    def test_result_column(self):
        self.write("a", make_record("Random Speedrun #1", T0, 1000, completed=True))
        self.write("b", make_record("Random Speedrun #2", T0 + 5000, 1000))
        import_records(self.cfg)
        self.assertEqual([r["result"] for r in self.rows()], ["finished", "reset"])

    def test_lan_cheat_run_kept_with_marker(self):
        self.write("a", make_record("Random Speedrun #1", T0, 400_000, cheats=True,
                                    open_lan=300_000, timelines=[("enter_nether", 200_000),
                                                                 ("enter_bastion", 350_000)]))
        import_records(self.cfg)
        row = self.rows()[0]
        self.assertEqual((row["nether"], row["bastion"], row["cheats_from_rta"]),
                         ("3:20.000", "", "5:00.000"))

    def test_record_changed_after_import_replaces_row(self):
        # World in progress at import time: only reached the nether so far.
        self.write("a", make_record("Random Speedrun #1", T0, 60_000,
                                    timelines=[("enter_nether", 50_000)]))
        import_records(self.cfg)
        # SpeedRunIGT rewrites the record later with more splits.
        self.write("a", make_record("Random Speedrun #1", T0 + 60_000, 120_000,
                                    timelines=[("enter_nether", 50_000), ("enter_bastion", 90_000)]))
        future = self.cfg.runs_csv(self.speedrun).stat().st_mtime + 10
        os.utime(self.cfg.records_dir / "a.json", (future, future))

        r = import_records(self.cfg).instances["speedrun"]
        self.assertEqual((r.added, r.updated, r.total), (0, 1, 1))
        row = self.rows()[0]
        self.assertEqual((row["nether"], row["bastion"]), ("0:50.000", "1:30.000"))

    def test_ignored_cache_skips_unchanged_records(self):
        self.write("a", make_record("Random Speedrun #1", T0, 1000))
        self.write("x", make_record("New World (2)", T0, 1000))
        ignored = {}
        import_records(self.cfg, ignored=ignored)
        self.assertIn("x", ignored)
        with mock.patch("icy_rsg_tracker.importer.load_record") as load:
            result = import_records(self.cfg, ignored=ignored)
            load.assert_not_called()
        self.assertEqual(result.ignored, {OTHER_INSTANCE: 1})

    def test_counter_restart(self):
        self.write("a", make_record("Random Speedrun #5000", T0, 1000))
        self.write("b", make_record("Random Speedrun #3", T0 + 5000, 1000))
        import_records(self.cfg)
        self.assertEqual([r["worlds_generated"] for r in self.rows()], ["1", "1"])

    def test_history_kept_when_records_deleted(self):
        self.write("a", make_record("Random Speedrun #1", T0, 1000))
        import_records(self.cfg)
        (self.cfg.records_dir / "a.json").unlink()
        self.write("b", make_record("Random Speedrun #2", T0 + 5000, 1000))
        self.assertEqual(import_records(self.cfg).instances["speedrun"].total, 2)


class StatsTest(unittest.TestCase):
    """One session: worlds #1-#10 generated, 3 played (all enter nether, 1 finishes),
    first run starts at T0, last run ends at T0 + 1h."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.cfg = Config(speedrunigt_dir=root / "speedrunigt", output_dir=root / "data")
        self.cfg.records_dir.mkdir(parents=True)
        records = {
            "a": make_record("Random Speedrun #1", T0 + 60_000, 60_000,
                             timelines=[("enter_nether", 120_000)]),
            "b": make_record("Random Speedrun #5", T0 + 600_000, 300_000,
                             timelines=[("enter_nether", 180_000), ("enter_bastion", 240_000)]),
            "c": make_record("Random Speedrun #10", T0 + 3_600_000, 1_200_000, completed=True,
                             timelines=[("enter_nether", 240_000)]),
            # Next day: a separate session
            "d": make_record("Random Speedrun #11", T0 + 86_400_000, 30_000),
        }
        for run_id, rec in records.items():
            (self.cfg.records_dir / f"{run_id}.json").write_text(json.dumps(rec))
        import_records(self.cfg)
        self.dir = self.cfg.instance_dir(self.cfg.instances[0])

    def tearDown(self):
        self.tmp.cleanup()

    def read(self, name):
        with open(self.dir / name, encoding="utf-8-sig") as f:
            return list(csv.DictReader(f))

    def test_session_stats(self):
        sessions = self.read("sessions.csv")
        self.assertEqual([s["session_id"] for s in sessions], ["1", "2"])
        s = sessions[0]
        expected = {
            "runs_played": "3", "worlds_generated": "10", "wall_resets": "7",
            "total_resets": "9", "finished": "1", "time_span": "1:00:00",
            "playtime": "0:26:00", "nethers_per_hour": "3.00", "resets_per_nether": "3.3",
            "nether_count": "3", "nether_rate": "100.0%", "nether_avg": "3:00.000",
            "nether_median": "3:00.000", "nether_best": "2:00.000",
            "bastion_count": "1", "bastion_rate": "33.3%", "bastion_best": "4:00.000",
            "fortress_count": "0", "fortress_rate": "0.0%", "fortress_avg": "",
            "finish_count": "1", "finish_rate": "33.3%", "finish_best": "19:59.990",
        }
        self.assertEqual({k: s[k] for k in expected}, expected)

    def test_run_left_paused_doesnt_stretch_session(self):
        # Ends 8h after run c, with 8h of real time but only 40s in-game: game left paused.
        rec = make_record("Random Speedrun #12", T0 + 3_600_000 + 8 * 3_600_000, 8 * 3_600_000)
        rec["final_igt"] = 40_000
        (self.cfg.records_dir / "e.json").write_text(json.dumps(rec))
        import_records(self.cfg)
        sessions = self.read("sessions.csv")
        # e starts its own session instead of extending session 1 to 9 hours.
        self.assertEqual(len(sessions), 3)
        self.assertEqual(sessions[0]["time_span"], "1:00:00")
        self.assertEqual((sessions[1]["runs_played"], sessions[1]["playtime"]), ("1", "0:00:40"))

    def test_structures_in_order_entered(self):
        from icy_rsg_tracker.stats import compute_raw
        rows = runs_csv.load_rows(self.cfg.runs_csv(self.cfg.instances[0]))
        row = dict(rows[0], bastion="", fortress="")
        both_fort_first = dict(row, nether="1:00.000", fortress="2:00.000", bastion="5:00.000")
        bastion_only = dict(row, nether="1:00.000", bastion="3:00.000")
        splits = compute_raw([both_fort_first, bastion_only], 30)["splits"]
        self.assertEqual((splits["structure1"]["count"], splits["structure1"]["best_ms"]), (2, 120_000))
        self.assertEqual((splits["structure2"]["count"], splits["structure2"]["best_ms"]), (1, 300_000))
        self.assertEqual(splits["structure1"]["avg_ms"], 150_000)  # 2:00 and 3:00
        # The CSV columns don't change.
        self.assertNotIn("structure1_count", [r["stat"] for r in self.read("stats.csv")])

    def test_windows(self):
        stats = {row["stat"]: row for row in self.read("stats.csv")}
        self.assertEqual(stats["runs_played"]["all_time"], "4")
        self.assertEqual(stats["runs_played"]["last_session"], "1")
        self.assertEqual(stats["nether_count"]["all_time"], "3")
        self.assertEqual(stats["nether_count"]["last_session"], "0")
        self.assertEqual(stats["nether_rate"]["last_session"], "0.0%")
        self.assertEqual(stats["nether_avg"]["last_session"], "")
        # Two sessions: 1h + 30s
        self.assertEqual(stats["time_span"]["all_time"], "1:00:30")


def log_world(n, body, player="Player", start="16:35:21"):
    """Minecraft log lines for one world: join, then body lines (time, thread, msg)."""
    lines = [
        f"[{start}] [Server thread #{n}/INFO]: {player} joined the game",
        f"[{start}] [Server thread #{n}/INFO]: Saving chunks for level "
        f"'ServerLevel[Random Speedrun #{n}]'/minecraft:overworld",
    ]
    for time_, thread, msg in body:
        thread = f"Server thread #{n}/INFO" if thread == "server" else "main/INFO"
        lines.append(f"[{time_}] [{thread}]: {msg}")
    lines.append(f"[23:59:00] [Server thread #{n}/INFO]: {player} left the game")
    return lines


class DeathsTest(unittest.TestCase):
    def test_plain_server_thread_without_seedqueue(self):
        # No SeedQueue: one unnumbered server thread; each join starts the next world.
        lines = [
            "[10:00:00] [Server thread/INFO]: Preparing start region for dimension minecraft:overworld",
            "[10:00:05] [Server thread/INFO]: Player joined the game",
            "[10:00:05] [Server thread/INFO]: Saving chunks for level 'ServerLevel[Random Speedrun #7]'/minecraft:overworld",
            "[10:01:00] [main/INFO]: [CHAT] Respawn point set",
            "[10:02:00] [Server thread/INFO]: Player hit the ground too hard",
            "[10:03:00] [Server thread/INFO]: Player left the game",
            "[10:03:01] [Server thread/INFO]: Saving chunks for level 'ServerLevel[Random Speedrun #7]'/minecraft:overworld",
            "[10:03:10] [Server thread/INFO]: Player joined the game",
            "[10:03:10] [Server thread/INFO]: Saving chunks for level 'ServerLevel[Random Speedrun #8]'/minecraft:overworld",
            "[10:04:00] [Server thread/INFO]: Player tried to swim in lava",
            "[10:05:00] [Server thread/INFO]: Player left the game",
        ]
        worlds = deaths.parse_log_lines(lines)
        self.assertEqual([d.respawn for d in deaths.classify(worlds["Random Speedrun #7"]).deaths], [True])
        self.assertEqual([d.respawn for d in deaths.classify(worlds["Random Speedrun #8"]).deaths], [False])

    def classify_world(self, body, n=1):
        worlds = deaths.parse_log_lines(log_world(n, body))
        return [(d.respawn, d.after_lan) for d in deaths.classify(worlds[f"Random Speedrun #{n}"]).deaths]

    def test_accidental_death_without_spawn(self):
        self.assertEqual(self.classify_world([
            ("16:40:00", "server", "Player tried to swim in lava"),
            ("16:40:00", "main", "[CHAT] Player tried to swim in lava"),
        ]), [(False, False)])

    def test_death_reset_with_bed(self):
        self.assertEqual(self.classify_world([
            ("16:51:28", "main", "[CHAT] Respawn point set"),
            ("16:51:30", "server", "Player hit the ground too hard"),
        ]), [(True, False)])

    def test_bed_gone_on_respawn_screen(self):
        # World #24882: spawn set, died, bed missing on respawn -> sent to world spawn.
        self.assertEqual(self.classify_world([
            ("16:51:28", "main", "[CHAT] Respawn point set"),
            ("16:52:57", "server", "Player was shot by Piglin"),
            ("16:53:00", "main", deaths.RESPAWN_FAILED),
        ]), [(False, False)])

    def test_no_bed_message_from_end_exit_portal_is_not_a_death(self):
        # World #21682: death reset before the End, then the exit portal after the dragon
        # says "no home bed" (bed was used up). The death still respawned at the bed.
        self.assertEqual(self.classify_world([
            ("20:38:14", "main", "[CHAT] Respawn point set"),
            ("20:38:19", "server", "Player hit the ground too hard"),
            ("20:38:58", "server", "Player has made the advancement [The End?]"),
            ("20:39:57", "main", deaths.RESPAWN_FAILED),
        ]), [(True, False)])

    def test_late_no_bed_message_without_activity_is_ignored(self):
        self.assertEqual(self.classify_world([
            ("20:38:14", "main", "[CHAT] Respawn point set"),
            ("20:38:19", "server", "Player hit the ground too hard"),
            ("20:45:00", "main", deaths.RESPAWN_FAILED),
        ]), [(True, False)])

    def test_failed_respawn_clears_spawn_point(self):
        self.assertEqual(self.classify_world([
            ("10:00:00", "main", "[CHAT] Respawn point set"),
            ("10:01:00", "server", "Player drowned"),
            ("10:01:02", "main", deaths.RESPAWN_FAILED),
            ("10:05:00", "server", "Player blew up"),
        ]), [(False, False), (False, False)])

    def test_deaths_after_lan_flagged(self):
        self.assertEqual(self.classify_world([
            ("10:00:00", "server", "Player drowned"),
            ("10:02:00", "main", "[CHAT] Local game hosted on port 58128"),
            ("10:03:00", "server", "Player fell out of the world"),
        ]), [(False, False), (False, True)])

    def test_non_death_messages_ignored(self):
        self.assertEqual(self.classify_world([
            ("10:00:00", "server", "Player has made the advancement [Stone Age]"),
            ("10:00:01", "server", "Player has completed the challenge [Return to Sender]"),
            ("10:00:02", "server", "Player lost connection: Disconnected"),
            ("10:00:03", "server", "Player moved wrongly!"),
        ]), [])

    def test_chat_only_counts_for_world_being_played(self):
        # SeedQueue generates other worlds in the background; chat belongs to the joined one.
        lines = (log_world(1, [("10:00:00", "main", "[CHAT] Respawn point set")])
                 + [f"[23:59:30] [Server thread #2/INFO]: Saving chunks for level "
                    f"'ServerLevel[Random Speedrun #2]'/minecraft:overworld",
                    "[23:59:31] [main/INFO]: [CHAT] Respawn point set"])
        worlds = deaths.parse_log_lines(lines)
        self.assertEqual(list(worlds), ["Random Speedrun #1"])

    def test_death_columns(self):
        world = deaths.WorldDeaths([deaths.Death(True, False), deaths.Death(False, False),
                                    deaths.Death(False, True)])
        self.assertEqual(deaths.death_columns(3, world, cheats=False), (3, 1, 2))
        self.assertEqual(deaths.death_columns(3, world, cheats=True), (2, 1, 1))
        self.assertEqual(deaths.death_columns(2, world, cheats=False), (2, None, None))  # mismatch
        self.assertEqual(deaths.death_columns(1, None, cheats=False), (1, None, None))   # no log
        self.assertEqual(deaths.death_columns(0, None, cheats=False), (0, 0, 0))

    def test_import_uses_logs_and_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            mc = root / "minecraft"
            (mc / "logs").mkdir(parents=True)
            cfg = Config(speedrunigt_dir=root / "speedrunigt", output_dir=root / "data",
                         instances=[Instance("speedrun", re.compile(r"^Random Speedrun"), mc)])
            cfg.records_dir.mkdir(parents=True)
            body = [("16:51:28", "main", "[CHAT] Respawn point set"),
                    ("16:51:30", "server", "Player hit the ground too hard"),
                    ("16:52:57", "server", "Player was shot by Piglin")]
            with gzip.open(mc / "logs" / "2026-11-24-1.log.gz", "wt", encoding="utf-8") as f:
                f.write("\n".join(log_world(7, body)) + "\n")
            rec = make_record("Random Speedrun #7", T0, 1000)
            rec["stats"] = {"uuid": {"stats": {"minecraft:custom": {"minecraft:deaths": 2}}}}
            (cfg.records_dir / "a.json").write_text(json.dumps(rec))

            import_records(cfg)
            row = runs_csv.load_rows(cfg.runs_csv(cfg.instances[0]))[0]
            self.assertEqual((row["deaths"], row["deaths_with_respawn"],
                              row["deaths_without_respawn"]), ("2", "2", "0"))
            self.assertTrue((cfg.instance_dir(cfg.instances[0]) / "log_cache.json").exists())

            # Second import of a changed record reads the .gz from the cache, not the file.
            os.utime(cfg.records_dir / "a.json", (time.time() + 10, time.time() + 10))
            with mock.patch.object(deaths, "_read_lines", side_effect=AssertionError):
                (mc / "logs" / "latest.log").unlink(missing_ok=True)
                import_records(cfg)


class WatchTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.cfg = Config(speedrunigt_dir=root / "speedrunigt", output_dir=root / "data")
        self.cfg.records_dir.mkdir(parents=True)

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, run_id, record):
        (self.cfg.records_dir / f"{run_id}.json").write_text(json.dumps(record))

    def test_describe_run(self):
        row = runs_csv.run_to_row(parse_record(make_record(
            "Random Speedrun #42", T0, 300_000, cheats=True, open_lan=290_000,
            timelines=[("enter_nether", 150_000), ("enter_bastion", 200_000)]), "a"))
        self.assertEqual(watch_mod.describe_run(row),
                         "#42 reset at 4:59.990 | nether 2:30.000 | bastion 3:20.000"
                         " | cheats (LAN) from 4:50.000 RTA")

    def test_watch_picks_up_new_record(self):
        self.write("a", make_record("Random Speedrun #1", T0, 60_000))
        lines = []
        sleeps = 0

        def fake_sleep(_):
            # First check: a run finishes. Second check: user presses Ctrl+C.
            nonlocal sleeps
            sleeps += 1
            if sleeps == 1:
                self.write("b", make_record("Random Speedrun #3", T0 + 120_000, 60_000,
                                            timelines=[("enter_nether", 45_000)]))
            else:
                raise KeyboardInterrupt

        with mock.patch.object(watch_mod.time, "sleep", fake_sleep), \
                mock.patch.object(watch_mod, "lower_priority"):
            watch_mod.watch(self.cfg, interval=0, out=lines.append)

        text = "\n".join(lines)
        self.assertIn("[speedrun] 1 runs; 1 new", text)
        self.assertIn("[speedrun] #3 reset at 0:59.990 | nether 0:45.000", text)
        self.assertIn("session 1: 2 played, 1 wall resets, 1 nethers", text)
        self.assertEqual(lines[-1], "Stopped.")
        rows = runs_csv.load_rows(self.cfg.runs_csv(self.cfg.instances[0]))
        self.assertEqual([r["run_id"] for r in rows], ["a", "b"])


if __name__ == "__main__":
    unittest.main()


class ResourcesTest(unittest.TestCase):
    def record(self, picked, crafted=None, dropped=None, mined=None, deaths=0, completed=False):
        stats = {"minecraft:picked_up": {f"minecraft:{k}": v for k, v in picked.items()},
                 "minecraft:crafted": {f"minecraft:{k}": v for k, v in (crafted or {}).items()},
                 "minecraft:dropped": {f"minecraft:{k}": v for k, v in (dropped or {}).items()},
                 "minecraft:mined": {f"minecraft:{k}": v for k, v in (mined or {}).items()},
                 "minecraft:custom": {"minecraft:deaths": deaths}}
        return {"is_completed": completed, "date": T0, "stats": {"uuid": {"stats": stats}}}

    def counts(self, rec):
        from icy_rsg_tracker.resources import resources
        return {k: v["count"] for k, v in resources(rec).items() if isinstance(v, dict)}

    def test_counts(self):
        rec = self.record({"blaze_rod": 7, "ender_pearl": 20, "string": 37, "acacia_log": 16,
                           "crying_obsidian": 33, "glowstone_dust": 31, "potion": 4, "splash_potion": 4,
                           "obsidian": 13},
                          crafted={"white_wool": 10}, dropped={"blaze_rod": 1, "glowstone_dust": 3})
        self.assertEqual(self.counts(rec), {"blaze_rods": 6, "ender_pearls": 20, "beds": 3,
                                            "respawn_anchors": 2, "fire_resistance": 8, "obsidian": 13})

    def test_beds_need_wool_of_one_colour_and_planks(self):
        rec = self.record({"red_wool": 5, "white_wool": 3, "oak_planks": 6, "red_bed": 2}, mined={"red_bed": 1})
        # 1 red + 1 white bed from wool (planks for exactly 2), plus 1 bed mined and picked up.
        self.assertEqual(self.counts(rec)["beds"], 3)

    def test_death_divisor(self):
        from icy_rsg_tracker.resources import pickup_divisor
        self.assertEqual(pickup_divisor(0, True), 1)
        self.assertEqual(pickup_divisor(1, False), 1)  # one death, reset: items left behind
        self.assertEqual(pickup_divisor(2, False), 2)  # picked up again once, left at the last
        self.assertEqual(pickup_divisor(2, True), 3)   # picked up again after both
        rec = self.record({"ender_pearl": 30}, deaths=2, completed=True)
        self.assertEqual(self.counts(rec)["ender_pearls"], 10)

    def test_estimate_allows_for_items_used_before_deaths(self):
        from icy_rsg_tracker.resources import estimate
        # 10 pearls, 2 used before one death, picked back up: 10 + 8 = 18 picked up.
        self.assertEqual(estimate(18, [2]), 10)
        self.assertEqual(estimate(18, [0]), 9)       # without usage: plain halving
        # Everything used before the death: nothing to pick up again, so it adds nothing.
        self.assertEqual(estimate(4, [5]), 4)

    def test_usage_rules(self):
        from icy_rsg_tracker.resources import _usage
        m = 60_000
        use = _usage({"bastion": 4 * m, "fortress": 8 * m, "blind": 11 * m, "stronghold": 14 * m})
        self.assertEqual([use["obsidian"](t * m) for t in (5, 12, 15)], [0, 10, 20])
        # Fire resistance from 7:00 (a minute before the fortress) to 14:00, 3:00 each.
        self.assertEqual([use["fire_resistance"](t * m) for t in (6, 7.5, 10.5, 16)], [0, 1, 2, 3])
        # Pearls: 2 from structure 1 (4:00) to 2 (8:00), 2 from blind (11:00) to stronghold (14:00).
        self.assertEqual([use["ender_pearls"](t * m) for t in (3, 6, 9, 12, 15)], [0, 1, 2, 3, 4])

    def test_death_times_used_when_known(self):
        rec = self.record({"obsidian": 30}, deaths=1, completed=True)
        rec["timelines"] = [{"name": "nether_travel_blind", "igt": 600_000, "rta": 600_000},
                            {"name": "enter_stronghold", "igt": 800_000, "rta": 800_000}]
        from icy_rsg_tracker.resources import resources
        # Died in the stronghold: 20 obsidian placed, so 30 = total + (total - 20) -> 25.
        self.assertEqual(resources(rec, [900_000])["obsidian"]["count"], 25)
        self.assertEqual(resources(rec)["obsidian"]["count"], 15)  # time unknown: halved

    def test_end_needs_six_blaze_rods(self):
        from icy_rsg_tracker.resources import resources
        rec = self.record({"blaze_rod": 12}, deaths=2, completed=True)  # 12 / 3 = 4
        self.assertEqual(resources(rec)["blaze_rods"]["count"], 4)
        rec["timelines"] = [{"name": "enter_end", "igt": 900_000, "rta": 900_000}]
        self.assertEqual(resources(rec)["blaze_rods"]["count"], 6)

    def test_nether_death_reset_uses_an_anchor(self):
        from icy_rsg_tracker.resources import resources
        rec = self.record({"crying_obsidian": 18, "glowstone_dust": 36}, deaths=1, completed=True)
        rec["timelines"] = [{"name": "enter_nether", "igt": 200_000, "rta": 200_000}]
        # A death reset in the nether: 6 crying obsidian and 12 dust used, then picked back up:
        # 18 = total + (total - 6) -> 12 crying; 36 = total + (total - 12) -> 24 dust (6 glowstone).
        res = resources(rec, [300_000], [True])
        self.assertEqual(res["respawn_anchors"]["count"], 2)
        self.assertEqual(resources(rec, [300_000], [False])["respawn_anchors"]["count"], 1)  # accidental: halved
