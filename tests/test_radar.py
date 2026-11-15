import importlib.util
import json
from pathlib import Path
import struct
import tempfile
import time
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("pixel_radar", Path(__file__).resolve().parents[1] / "radar.py")
r = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)


def png(size=256):
    return r.PNG + struct.pack(">I", 13) + b"IHDR" + struct.pack(">II", size, size) + bytes(13) + bytes(4) + b"IEND" + bytes(4)


def api(stamp=None):
    stamp = int(time.time()) - 600 if stamp is None else stamp
    return {"host": r.RADAR_HOST, "radar": {"past": [{"time": stamp, "path": f"/v2/radar/{stamp}"}]}}


class RadarTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.old = r.STATE, r.CACHE
        r.STATE = Path(self.temp.name) / "state"
        r.CACHE = Path(self.temp.name) / "cache"
        self.city = {"name": '<img src="https://evil.test/tracker">', "latitude": 45.75, "longitude": 4.85}

    def tearDown(self):
        r.STATE, r.CACHE = self.old
        self.temp.cleanup()

    def test_disabled_radar_never_contacts_network(self):
        with patch.object(r, "download") as download:
            result = r.main(["load", json.dumps(self.city)])
            self.assertFalse(result["settings"]["enabled"])
            self.assertEqual(result["frames"], [])
            download.assert_not_called()

    def test_settings_are_bounded_and_persisted_separately(self):
        r.save_json(r.STATE / "settings.json", {"cities": [self.city]})
        prefs = r.configure({"enabled": True, "zoom": 7})
        self.assertEqual(r.settings(), prefs)
        self.assertEqual(r.read_json(r.STATE / "settings.json", {})["cities"], [self.city])
        for change in ({"enabled": "yes"}, {"zoom": 8}, {"zoom": True}, []):
            with self.assertRaises(ValueError):
                r.configure(change)

    def test_bad_coordinates_and_nonfinite_values_are_rejected(self):
        for lat, lon in ((91, 1), (0, 181), (float("nan"), 1), (0, float("inf"))):
            with self.assertRaises(ValueError):
                r.coordinates({"latitude": lat, "longitude": lon})

    def test_manifest_refuses_forecast_paths_host_injection_and_future(self):
        now = int(time.time())
        for value in (
            {"host": "https://evil.test", "radar": api()["radar"]},
            {"host": r.RADAR_HOST, "radar": {"past": [{"time": now, "path": "/../../passwd"}]}},
            api(now + 3600),
            api(now - 90000),
            {"host": r.RADAR_HOST, "radar": {"past": [{"time": now, "path": "/v2/radar/x?redirect=evil"}]}},
        ):
            with self.assertRaises(ValueError):
                r.validate_manifest(value)
        value = api(now - 600)
        value["radar"]["nowcast"] = [{"time": now + 600, "path": f"/v2/radar/{now+600}"}]
        self.assertEqual(len(r.validate_manifest(value)["radar"]["past"]), 1)
        value["radar"]["past"][0]["path"] = "/v2/radar/cd6d910dedfd"
        self.assertEqual(r.validate_manifest(value)["radar"]["past"][0]["path"], "/v2/radar/cd6d910dedfd")

    def test_viewport_wraps_dateline_refuses_poles_and_only_loads_visible_tiles(self):
        for lat, lon in ((45.75, 4.85), (85, 180), (-85, -180), (0, 0)):
            tiles = r.viewport(lat, lon, 6)
            self.assertLessEqual(len(tiles), 6)
            self.assertTrue(all(0 <= t["x"] < 64 and 0 <= t["y"] < 64 for t in tiles))
            self.assertTrue(all(t["left"] < 432 and t["left"] + 256 > 0 and t["top"] < 240 and t["top"] + 256 > 0 for t in tiles))
        for lat in (-90, 90):
            with self.assertRaises(ValueError): r.viewport(lat, 0, 6)

    def test_png_validation_rejects_html_huge_dimensions_truncation(self):
        self.assertTrue(r.valid_png(png()))
        for content in (b"<html>error</html>", png(8192), png()[:-12], png() + b"bad"):
            self.assertFalse(r.valid_png(content))

    def test_live_load_and_cached_offline_manifest_keep_animation(self):
        r.configure({"enabled": True})
        response = api()
        stamp = response["radar"]["past"][0]["time"] - 600
        response["radar"]["past"].insert(0, {"time": stamp, "path": f"/v2/radar/{stamp}"})
        def download(url, limit):
            return json.dumps(response).encode() if url == r.MANIFEST_URL else png()
        with patch.object(r, "download", side_effect=download) as fetch:
            result = r.load(self.city)
            self.assertEqual(len(result["frames"]), 2)
            self.assertFalse(result["stale"])
            self.assertTrue(all(tile["source"].startswith("file://") for tile in result["tiles"]))
            first_calls = fetch.call_count
            r.load(self.city)
            self.assertEqual(fetch.call_count, first_calls)
        path = r.CACHE / "manifest.json"
        import os
        os.utime(path, (time.time() - 600, time.time() - 600))
        with patch.object(r, "download", side_effect=OSError("offline")) as fetch:
            result = r.load(self.city)
            self.assertTrue(result["stale"])
            self.assertEqual(len(result["frames"]), 2)
            self.assertEqual(fetch.call_count, 1)

    def test_osm_tiles_are_cached_for_at_least_seven_days(self):
        url = r.OSM_HOST + "/6/32/20.png"
        with patch.object(r, "download", return_value=png()) as fetch:
            result = r.tile(url, osm=True)
            import os
            path = Path(result.removeprefix("file://"))
            os.utime(path, (time.time() - 6 * 86400, time.time() - 6 * 86400))
            self.assertEqual(r.tile(url, osm=True), result)
            self.assertEqual(fetch.call_count, 1)

    def test_rate_limit_is_shared_and_fails_without_sleeping(self):
        r.save_json(r.CACHE / "requests.json", [time.time()] * 90)
        with self.assertRaises(OSError):
            with r.rate_guard():
                pass

    def test_pressure_prunes_radar_before_protected_osm_tiles(self):
        base = r.CACHE / "osm-" / "base.png"
        radar = r.CACHE / "radar-" / "frame.png"
        r.save_bytes(base, png())
        r.save_bytes(radar, png())
        with patch.object(r, "MAX_CACHE_BYTES", len(png()) + 1):
            r.prune_cache()
        self.assertTrue(base.exists())
        self.assertFalse(radar.exists())

    def test_full_osm_quota_refuses_new_download_without_evicting_recent_tiles(self):
        base = r.CACHE / "osm-" / "protected.png"
        r.save_bytes(base, png())
        with patch.object(r, "OSM_CACHE_BYTES", len(png()) + 1), patch.object(r, "download") as download:
            self.assertIsNone(r.tile(r.OSM_HOST + "/6/33/20.png", osm=True))
            download.assert_not_called()
        self.assertTrue(base.exists())

    def test_partial_frames_are_not_shown_with_missing_tiles(self):
        r.configure({"enabled": True})
        with patch.object(r, "manifest", return_value=(api(), False)), patch.object(r, "tile", return_value=None):
            result = r.load(self.city)
        self.assertEqual(result["frames"], [])
        self.assertTrue(result["partial"])
        self.assertIn("error", result)

    def test_redirect_to_untrusted_host_is_rejected(self):
        with self.assertRaises(ValueError):
            r.SafeRedirect().redirect_request(None, None, 302, "Found", {}, "https://evil.test/tile.png")

    def test_radar_qml_uses_only_plain_text_and_local_images(self):
        qml = (Path(__file__).resolve().parents[1] / "Radar.qml").read_text()
        self.assertNotIn("Text {", qml.replace("PText {", ""))
        self.assertIn('root.active && root.radarEnabled', qml)
        self.assertIn('OpenStreetMap contributors', qml)
        self.assertIn('RainViewer', qml)


if __name__ == "__main__":
    unittest.main()
