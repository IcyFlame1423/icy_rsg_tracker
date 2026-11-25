import http.client
import json
import re
import tempfile
import threading
import unittest
from pathlib import Path

from icy_rsg_tracker import settings
from icy_rsg_tracker.app.server import App, serve
from icy_rsg_tracker.config import Config, Instance, load_config
from icy_rsg_tracker.watch import Tracker

from .test_tracker import T0, make_record


def valid(**overrides):
    body = {
        "speedrunigt_dir": "C:/Users/someone/speedrunigt",
        "session_gap_minutes": 45, "watch_interval_seconds": 2, "include_set_seed": False,
        # A name with no Prism instance on any machine, so the Minecraft folder stays unset.
        "instances": [{"name": "rsg-test-zz", "world_name_pattern": settings.RSG_PATTERN, "minecraft_dir": ""}],
    }
    body.update(overrides)
    return body


class ParseTest(unittest.TestCase):
    def test_valid(self):
        v = settings.parse(valid())
        self.assertEqual((v["session_gap_minutes"], v["watch_interval_seconds"]), (45, 2))
        self.assertEqual(v["instances"][0].name, "rsg-test-zz")
        self.assertIsNone(v["instances"][0].minecraft_dir)

    def test_errors_per_field(self):
        bad = valid(session_gap_minutes=0, watch_interval_seconds="x", speedrunigt_dir=" ",
                    instances=[{"name": "../escape", "world_name_pattern": "("},
                               {"name": "ok", "world_name_pattern": "x", "minecraft_dir": "Z:/nope/nope"},
                               {"name": "OK", "world_name_pattern": ""}])
        with self.assertRaises(settings.SettingsError) as ctx:
            settings.parse(bad)
        e = ctx.exception.errors
        self.assertEqual(set(e), {"session_gap_minutes", "watch_interval_seconds", "speedrunigt_dir",
                                  "instances.0.name", "instances.0.world_name_pattern",
                                  "instances.1.minecraft_dir", "instances.2.name",
                                  "instances.2.world_name_pattern"})
        self.assertIn("already has this name", e["instances.2.name"])

    def test_needs_an_instance(self):
        with self.assertRaises(settings.SettingsError) as ctx:
            settings.parse(valid(instances=[]))
        self.assertIn("instances", ctx.exception.errors)


class TomlTest(unittest.TestCase):
    def test_round_trip(self):
        with tempfile.TemporaryDirectory() as tmp:
            mc = Path(tmp) / "it's a folder (2)"  # quotes aren't allowed in Windows names
            mc.mkdir()
            cfg = Config(path=Path(tmp) / "config.toml", speedrunigt_dir=Path("C:/Users/a b/speedrunigt"),
                         session_gap_minutes=12.5, watch_interval_seconds=4, include_set_seed=True,
                         instances=[Instance("rsg-test-zz", re.compile(r'^Random Speedrun #\d+$')),
                                    Instance("ranked", re.compile(r'^(New World|mcsrranked) "x"'), mc)])
            settings.save(cfg)
            back = load_config(cfg.path)
            self.assertEqual(back.speedrunigt_dir, cfg.speedrunigt_dir)
            self.assertEqual((back.session_gap_minutes, back.watch_interval_seconds, back.include_set_seed),
                             (12.5, 4, True))
            self.assertEqual([(i.name, i.world_name_pattern.pattern, i.minecraft_dir) for i in back.instances],
                             [(i.name, i.world_name_pattern.pattern, i.minecraft_dir) for i in cfg.instances])


class DetectTest(unittest.TestCase):
    def test_detects_rsg_instances(self):
        with tempfile.TemporaryDirectory() as tmp:
            launcher = Path(tmp) / "instances"
            (launcher / "rsg" / "minecraft" / "mods").mkdir(parents=True)
            (launcher / "rsg" / "minecraft" / "mods" / "atum-2.0.jar").write_text("")
            (launcher / "other" / ".minecraft" / "saves" / "New World").mkdir(parents=True)
            (launcher / "not-an-instance").mkdir()
            found = {f["name"]: f for f in settings.detect_instances([launcher]) if f["launcher"] == str(launcher)}
            self.assertEqual(set(found), {"rsg", "other"})
            self.assertTrue(found["rsg"]["rsg"])
            self.assertEqual(found["rsg"]["world_name_pattern"], settings.RSG_PATTERN)
            self.assertFalse(found["other"]["rsg"])
            self.assertTrue(found["other"]["minecraft_dir"].endswith(".minecraft"))


class TrackerFolderTest(unittest.TestCase):
    def test_missing_records_folder_then_fixed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cfg = Config(speedrunigt_dir=root / "speedrunigt", output_dir=root / "data")
            lines = []
            t = Tracker(cfg, out=lines.append)
            t.start()  # no crash
            self.assertIn("not found", t.warning)
            cfg.records_dir.mkdir(parents=True)
            (cfg.records_dir / "a.json").write_text(json.dumps(make_record("Random Speedrun #1", T0, 1000)))
            t.check()
            self.assertIsNone(t.warning)
            self.assertTrue(cfg.runs_csv(cfg.instances[0]).exists())


class SettingsApiTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.cfg = Config(path=root / "config.toml", speedrunigt_dir=root / "speedrunigt",
                          output_dir=root / "data")
        self.cfg.records_dir.mkdir(parents=True)
        (self.cfg.records_dir / "a.json").write_text(json.dumps(make_record("Random Speedrun #1", T0, 1000)))
        self.app = App(self.cfg, track=False, out=lambda line: None)
        self.httpd = serve(self.app, port=18865)
        self.port = self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.tmp.cleanup()

    def request(self, method, path, body=None, content_type="application/json", origin=None):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        headers = {"Content-Type": content_type}
        if origin:
            headers["Origin"] = origin
        payload = json.dumps(body).encode() if body is not None else None
        conn.request(method, path, body=payload, headers=headers)
        res = conn.getresponse()
        data = res.read()
        conn.close()
        return res.status, (json.loads(data) if data[:1] in (b"{", b"[") else data)

    def test_get_settings(self):
        status, body = self.request("GET", "/api/settings")
        self.assertEqual(status, 200)
        self.assertEqual(body["records_found"], 1)
        self.assertEqual(body["instances"][0]["name"], "speedrun")

    def test_save(self):
        body = valid(speedrunigt_dir=str(self.cfg.speedrunigt_dir), session_gap_minutes=20)
        status, out = self.request("POST", "/api/settings", body, origin=f"http://127.0.0.1:{self.port}")
        self.assertEqual(status, 200, out)
        self.assertEqual(self.cfg.session_gap_minutes, 20)  # applied live
        self.assertEqual(load_config(self.cfg.path).session_gap_minutes, 20)  # and saved

    def test_invalid_save_changes_nothing(self):
        status, out = self.request("POST", "/api/settings", valid(session_gap_minutes=-5))
        self.assertEqual(status, 400)
        self.assertIn("session_gap_minutes", out["fields"])
        self.assertEqual(self.cfg.session_gap_minutes, 30)
        self.assertFalse(self.cfg.path.exists())

    def test_cross_site_requests_rejected(self):
        # A form post from another site can't send JSON without permission...
        status, _ = self.request("POST", "/api/settings", valid(), content_type="text/plain")
        self.assertEqual(status, 403)
        # ...and a JSON request from another origin is refused.
        status, _ = self.request("POST", "/api/rebuild", {}, origin="https://evil.example")
        self.assertEqual(status, 403)

    def test_rebuild(self):
        status, out = self.request("POST", "/api/rebuild", {})
        self.assertEqual(status, 200, out)
        self.assertEqual(out["runs"], {"speedrun": 1})


if __name__ == "__main__":
    unittest.main()
