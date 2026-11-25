import http.client
import json
import tempfile
import threading
import unittest
from datetime import datetime
from pathlib import Path

from icy_rsg_tracker.app import data
from icy_rsg_tracker.app.server import App, serve
from icy_rsg_tracker.config import Config
from icy_rsg_tracker.importer import import_records

from .test_tracker import T0, make_record

NOW = datetime.fromtimestamp((T0 + 86_400_000 + 60_000) / 1000)  # just after the last run


class AppTestBase(unittest.TestCase):
    """Two sessions: 3 runs at T0 (one nether), 1 run a day later."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.cfg = Config(speedrunigt_dir=root / "speedrunigt", output_dir=root / "data")
        self.cfg.records_dir.mkdir(parents=True)
        records = {
            "a": make_record("Random Speedrun #1", T0 + 60_000, 60_000,
                             timelines=[("enter_nether", 50_000)]),
            "b": make_record("Random Speedrun #3", T0 + 180_000, 60_000),
            "c": make_record("Random Speedrun #4", T0 + 300_000, 60_000),
            "d": make_record("Random Speedrun #9", T0 + 86_400_000, 30_000),
        }
        for run_id, rec in records.items():
            (self.cfg.records_dir / f"{run_id}.json").write_text(json.dumps(rec))
        import_records(self.cfg)
        self.store = data.DataStore(self.cfg)

    def tearDown(self):
        self.tmp.cleanup()


class DataTest(AppTestBase):
    def test_windows(self):
        rows = self.store.rows("speedrun")
        ids = lambda w, **kw: [r["run_id"] for r in data.select_window(rows, w, now=NOW, **kw)]
        self.assertEqual(ids("all"), ["a", "b", "c", "d"])
        self.assertEqual(ids("last_session"), ["d"])
        self.assertEqual(ids("today"), ["d"])
        self.assertEqual(ids("7d"), ["a", "b", "c", "d"])
        self.assertEqual(ids("1y"), ["a", "b", "c", "d"])
        self.assertEqual(data.select_window(rows, "1y", now=NOW.replace(year=NOW.year + 2)), [])
        day0 = datetime.fromtimestamp(T0 / 1000).strftime("%Y-%m-%d")
        self.assertEqual(ids("custom", start=day0, end=day0), ["a", "b", "c"])
        self.assertEqual(ids("session", session="1"), ["a", "b", "c"])
        self.assertEqual(ids("session", session="2"), ["d"])
        self.assertEqual(ids("session", session="9"), [])

    def test_bad_windows(self):
        rows = self.store.rows("speedrun")
        for kwargs in ({"window": "session"}, {"window": "session", "session": "x"},
                       {"window": "week"}, {"window": "custom", "start": "x", "end": "y"},
                       {"window": "custom", "start": "2026-11-24", "end": "2026-11-01"}):
            with self.assertRaises(data.BadRequest):
                data.select_window(rows, **kwargs)
        with self.assertRaises(data.BadRequest):
            self.store.rows("nope")

    def test_summary(self):
        s = data.summary(self.store, "speedrun", "all", now=NOW)
        self.assertEqual(s["total_runs"], 4)
        st = s["stats"]
        self.assertEqual((st["runs_played"], st["worlds_generated"], st["wall_resets"]), (4, 9, 5))
        self.assertEqual(st["splits"]["nether"]["count"], 1)
        self.assertAlmostEqual(st["splits"]["nether"]["rate"], 0.25)
        self.assertEqual(st["splits"]["nether"]["best_ms"], 50_000)
        self.assertEqual(st["splits"]["bastion"]["count"], 0)
        self.assertIsNone(st["splits"]["bastion"]["avg_ms"])
        self.assertEqual([x["session_id"] for x in s["sessions"]], [1, 2])
        self.assertEqual(s["sessions"][0]["splits"]["nether"],
                         {"count": 1, "avg_ms": 50_000, "best_ms": 50_000, "segment_avg_ms": None})
        self.assertEqual(s["sessions"][1]["splits"]["nether"],
                         {"count": 0, "avg_ms": None, "best_ms": None, "segment_avg_ms": None})
        self.assertEqual((s["sessions"][0]["runs_played"], s["sessions"][0]["wall_resets"]), (3, 1))
        self.assertEqual(set(s["sessions"][0]["splits"]),
                         {"nether", "bastion", "fortress", "blind", "stronghold", "end", "finish",
                          "structure1", "structure2"})

    def test_runs(self):
        r = data.runs(self.store, "speedrun", "all")
        self.assertEqual([x["run_id"] for x in r["runs"]], ["a", "b", "c", "d"])
        a = r["runs"][0]
        self.assertEqual((a["session_id"], a["world_number"], a["result"]), (1, 1, "reset"))
        self.assertEqual(a["splits"]["nether"], 50_000)
        self.assertIsNone(a["splits"]["bastion"])
        self.assertEqual((a["final_igt"], a["deaths"], a["advancements"]), (59_990, 0, {}))
        self.assertEqual(r["pbs"]["nether"], {"ms": 50_000, "run_id": "a"})
        self.assertNotIn("finish", r["pbs"])
        self.assertNotIn("structure1", r["pbs"])  # no run entered a bastion or fortress
        self.assertEqual(r["from_pbs"]["nether"], {})  # no run reached two splits
        # PBs are all-time even when the window is narrower.
        self.assertEqual(data.runs(self.store, "speedrun", "last_session")["pbs"], r["pbs"])
        self.assertEqual(len(r["advancements"]), 80)
        self.assertIn({"id": "story/iron_tools", "name": "Isn't It Iron Pick"}, r["advancements"])
        # Best time for each advancement any run got.
        best = {}
        for run in r["runs"]:
            for adv, ms in run["advancements"].items():
                if adv not in best or ms < best[adv]["ms"]:
                    best[adv] = {"ms": ms, "run_id": run["run_id"]}
        self.assertEqual(r["advancement_pbs"], best)

    def test_run_detail(self):
        d = data.run_detail(self.store, "speedrun", "a")
        self.assertEqual(d["run"]["run_id"], "a")
        self.assertEqual(d["times"]["nether"], 50_000)
        self.assertIsNone(d["times"]["structure1"])
        self.assertEqual(d["structures"], [])
        self.assertEqual(d["session"], {"id": 1, "position": 1, "runs": 3})
        self.assertEqual((d["previous_nether_run"], d["next_nether_run"]), (None, None))
        nether = d["compare"]["all"]["splits"]["nether"]
        self.assertEqual((nether["count"], nether["avg_ms"], nether["rank"]), (1, 50_000, 1))
        self.assertEqual(d["compare"]["session"]["runs"], 3)
        self.assertEqual(data.run_detail(self.store, "speedrun", "d")["previous_nether_run"], "a")
        with self.assertRaises(data.BadRequest):
            data.run_detail(self.store, "speedrun", "nope")

    def test_sessions_newest_first(self):
        s = data.sessions(self.store, "speedrun", "all")
        self.assertEqual([x["session_id"] for x in s["sessions"]], [2, 1])

    def test_empty_window(self):
        s = data.summary(self.store, "speedrun", "custom", "2020-01-01", "2020-01-02")
        self.assertEqual(s["stats"]["runs_played"], 0)
        self.assertIsNone(s["first_run"])
        self.assertEqual(s["sessions"], [])

    def test_rows_reloaded_when_csv_changes(self):
        first = self.store.rows("speedrun")
        self.assertIs(self.store.rows("speedrun"), first)  # cached
        (self.cfg.records_dir / "e.json").write_text(json.dumps(
            make_record("Random Speedrun #10", T0 + 86_500_000, 1000)))
        import_records(self.cfg)
        self.assertEqual(len(self.store.rows("speedrun")), 5)


class ServerTest(AppTestBase):
    def setUp(self):
        super().setUp()
        self.app = App(self.cfg, track=False, out=lambda line: None)
        self.httpd = serve(self.app, port=18765)
        self.port = self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        super().tearDown()

    def get(self, path, host=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        conn.putrequest("GET", path, skip_host=True)
        conn.putheader("Host", host or f"127.0.0.1:{self.port}")
        conn.endheaders()
        res = conn.getresponse()
        body = res.read()
        conn.close()
        return res.status, res.getheader("Content-Type"), body

    def test_api(self):
        status, ctype, body = self.get("/api/summary?window=all")
        self.assertEqual((status, ctype), (200, "application/json"))
        self.assertEqual(json.loads(body)["stats"]["runs_played"], 4)
        status, _, body = self.get("/api/runs?window=session&session=1")
        self.assertEqual([r["run_id"] for r in json.loads(body)["runs"]], ["a", "b", "c"])
        status, _, body = self.get("/api/sessions?window=all")
        self.assertEqual(len(json.loads(body)["sessions"]), 2)
        status, _, body = self.get("/api/status")
        self.assertEqual(json.loads(body)["instances"], ["speedrun"])
        st = json.loads(body)
        from icy_rsg_tracker import __version__
        self.assertEqual(st["app_version"], __version__)
        self.assertIn("speedrun", st["ongoing"])

    def test_stops_when_the_last_tab_closes(self):
        from icy_rsg_tracker.app.server import CLOSE_GRACE, PAGE_TIMEOUT
        stops = []
        self.app.on_stop = lambda: stops.append(1)
        self.app.auto_stop = True
        self.app.check_pages(now=0)
        self.assertFalse(self.app.stop.is_set())  # no tab yet: keep waiting for one
        self.app.status("tab1")
        self.app.status("tab2")
        self.app.page_closed("tab1")
        self.app.check_pages(now=self.app.last_close + CLOSE_GRACE + 1)
        self.assertFalse(self.app.stop.is_set())  # tab2 is still open
        self.app.page_closed("tab2")
        self.app.check_pages(now=self.app.last_close + 1)
        self.assertFalse(self.app.stop.is_set())  # maybe a refresh: wait for it to reconnect
        self.app.status("tab3")
        self.app.check_pages(now=self.app.pages["tab3"] + PAGE_TIMEOUT + 1)  # tab3 went silent
        self.app.check_pages(now=self.app.last_close + CLOSE_GRACE + 1)
        self.assertTrue(self.app.stop.is_set())

    def test_stop_button(self):
        stops = []
        self.app.on_stop = lambda: stops.append(1)
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        conn.request("POST", "/api/stop", body="{}", headers={"Content-Type": "application/json",
                                                               "Host": f"127.0.0.1:{self.port}"})
        self.assertEqual(conn.getresponse().status, 200)
        conn.close()
        self.assertTrue(self.app.stop.is_set())

    def test_session_ongoing(self):
        from datetime import timedelta
        from icy_rsg_tracker.stats import run_end
        last = run_end(self.store.rows("speedrun")[-1])
        gap = timedelta(minutes=self.cfg.session_gap_minutes)
        self.assertTrue(self.app.session_ongoing("speedrun", now=last + gap - timedelta(minutes=1)))
        self.assertFalse(self.app.session_ongoing("speedrun", now=last + gap + timedelta(minutes=1)))

    def test_bad_request(self):
        status, _, body = self.get("/api/summary?window=nope")
        self.assertEqual(status, 400)
        self.assertIn("window must be", json.loads(body)["error"])

    def test_static_files(self):
        status, ctype, body = self.get("/")
        self.assertEqual((status, ctype), (200, "text/html; charset=utf-8"))
        self.assertIn(b"Icy RSG Tracker", body)
        self.assertEqual(self.get("/app.js")[1], "text/javascript; charset=utf-8")

    def test_no_path_traversal(self):
        for path in ("/../server.py", "/..%2Fserver.py", "/../../config.py"):
            self.assertEqual(self.get(path)[0], 404, path)

    def test_port_not_shared(self):
        # A second server must not bind a port that's in use (Windows SO_REUSEADDR).
        with self.assertRaises(OSError):
            serve(self.app, port=self.port, tries=1)
        second = serve(self.app, port=self.port, tries=2)
        self.assertEqual(second.server_address[1], self.port + 1)
        second.server_close()

    def test_detects_running_instance(self):
        from icy_rsg_tracker.app.server import running_instance
        self.assertEqual(running_instance(self.port), f"http://127.0.0.1:{self.port}/")
        self.assertIsNone(running_instance(1))  # nothing there

    def test_foreign_host_rejected(self):
        self.assertEqual(self.get("/api/status", host="evil.example:80")[0], 403)
        self.assertEqual(self.get("/api/status", host=f"localhost:{self.port}")[0], 200)


if __name__ == "__main__":
    unittest.main()


class PlayerTest(unittest.TestCase):
    def setUp(self):
        from icy_rsg_tracker.app import player
        import re
        from icy_rsg_tracker.config import Instance
        self.player = player
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.inst = Instance("speedrun", re.compile(r"^Random Speedrun #d+$"), self.root)
        player._failed.clear()

    def tearDown(self):
        self.tmp.cleanup()

    def write_cache(self, entries):
        (self.root / "usercache.json").write_text(json.dumps(entries))

    def test_latest_entry_is_the_player(self):
        self.assertIsNone(self.player.player(self.inst))
        self.write_cache([
            {"name": "Old", "uuid": "11111111-1111-1111-1111-111111111111", "expiresOn": "2026-01-01 00:00:00 +0000"},
            {"name": "New", "uuid": "22222222-2222-2222-2222-222222222222", "expiresOn": "2026-12-01 00:00:00 +0000"},
            {"name": "Bad", "uuid": "not-a-uuid", "expiresOn": "2027-01-01 00:00:00 +0000"},
        ])
        self.assertEqual(self.player.player(self.inst)["name"], "New")

    def test_skin_cached_and_kept_when_offline(self):
        self.write_cache([{"name": "P", "uuid": "22222222-2222-2222-2222-222222222222", "expiresOn": "x"}])
        cache = self.root / "data"
        png = b"\x89PNG fake"
        self.assertEqual(self.player.skin(self.inst, cache, download=lambda u: png), png)

        def offline(uuid):
            raise OSError("offline")
        self.assertEqual(self.player.skin(self.inst, cache, download=offline), png)  # still fresh
        meta = json.loads((cache / "skin.json").read_text())
        meta["fetched"] = 0  # stale: tries again, fails, keeps the cached one
        (cache / "skin.json").write_text(json.dumps(meta))
        self.assertEqual(self.player.skin(self.inst, cache, download=offline), png)


class TexturesTest(unittest.TestCase):
    def test_reads_from_jar_and_rejects_bad_names(self):
        import re
        import zipfile
        from icy_rsg_tracker.app import textures
        from icy_rsg_tracker.config import Instance
        with tempfile.TemporaryDirectory() as tmp:
            launcher = Path(tmp) / "Prism"
            mc = launcher / "instances" / "speedrun" / "minecraft"
            mc.mkdir(parents=True)
            jar = launcher / "libraries/com/mojang/minecraft/1.16.1/minecraft-1.16.1-client.jar"
            jar.parent.mkdir(parents=True)
            with zipfile.ZipFile(jar, "w") as z:
                z.writestr("assets/minecraft/textures/item/ender_eye.png", b"\x89PNG eye")
            cfg = Config(instances=[Instance("speedrun", re.compile("x"), mc)])
            t = textures.Textures(lambda: cfg)
            self.assertEqual(t.jar(), jar)
            self.assertEqual(t.get("item/ender_eye"), b"\x89PNG eye")
            self.assertIsNone(t.get("item/missing"))
            self.assertIsNone(t.get("../../config"))
            self.assertIsNone(t.get("item/../x"))
