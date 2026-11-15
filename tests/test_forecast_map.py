import importlib.util
import json
import math
import os
from pathlib import Path
import struct
import sys
import tempfile
import time
import unittest
from urllib.parse import parse_qs, urlsplit
from unittest.mock import patch
import zlib

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
spec = importlib.util.spec_from_file_location("pixel_forecast_map", Path(__file__).resolve().parents[1] / "forecast_map.py")
f = importlib.util.module_from_spec(spec)
spec.loader.exec_module(f)


def png(width=432, height=240):
    def chunk(kind, body):
        return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body) & 0xffffffff)
    raw = (b"\x00" + bytes([50, 100, 200, 180]) * width) * height
    return (f.radar.PNG + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b""))


def capability(layer="precipitation", now=None):
    now = int(time.time()) if now is None else now
    reference = now // 43200 * 43200
    return {"layer": layer, "reference": reference,
            "times": list(range(reference, reference + 72 * 3600 + 1, 3600))}


def xml(layer="precipitation", now=None):
    value = capability(layer, now)
    spec = f.LAYERS[layer]
    return (f'<WMS_Capabilities xmlns="http://www.opengis.net/wms"><Capability><Layer><Layer>'
            f'<Name>{spec["name"]}</Name><Dimension name="time" units="ISO8601">'
            + ",".join(f.iso_time(t) for t in value["times"])
            + f'</Dimension><Dimension name="reference_time" default="{f.iso_time(value["reference"])}">'
            + f'{f.iso_time(value["reference"])}/{f.iso_time(value["reference"])}/PT12H</Dimension>'
            + f'<Style><Name>{spec["style"]}</Name></Style></Layer></Layer></Capability></WMS_Capabilities>').encode()


class ForecastMapTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.old = f.STATE, f.CACHE, f.radar.CACHE
        f.STATE = Path(self.temporary.name) / "state"
        f.CACHE = Path(self.temporary.name) / "cache"
        f.radar.CACHE = Path(self.temporary.name) / "radar-cache"
        self.city = {"name": '<img src="https://evil.invalid/probe">', "latitude": 45.75, "longitude": 4.85}

    def tearDown(self):
        f.STATE, f.CACHE, f.radar.CACHE = self.old
        self.temporary.cleanup()

    def fake_download(self, url, limit):
        query = parse_qs(urlsplit(url).query)
        action = query["REQUEST"][0]
        if action == "GetCapabilities":
            layer = next(k for k, spec in f.LAYERS.items() if spec["name"] == query["LAYERS"][0])
            return xml(layer)
        if action == "GetLegendGraphic":
            return png(107, 405)
        return png(int(query["WIDTH"][0]), int(query["HEIGHT"][0]))

    def test_disabled_never_uses_network_or_creates_state(self):
        with patch.object(f, "download") as network, patch.object(f.radar, "tile") as tile:
            result = f.main(["load", json.dumps(self.city)])
        self.assertFalse(result["settings"]["enabled"])
        self.assertFalse(result["frames"])
        network.assert_not_called()
        tile.assert_not_called()
        self.assertFalse(f.STATE.exists())

    def test_settings_are_separate_strict_and_corruption_is_normalized(self):
        f.save_json(f.STATE / "settings.json", {"city": self.city})
        saved = f.configure({"enabled": True, "zoom": 7, "layer": "temperature"})
        self.assertEqual(f.settings(), saved)
        self.assertEqual(f.read_json(f.STATE / "settings.json", {})["city"], self.city)
        for invalid in ({"enabled": 1}, {"zoom": True}, {"zoom": 8}, {"layer": "../evil"}, {"layer": []}, []):
            with self.assertRaises(ValueError):
                f.configure(invalid)
        f.save_json(f.STATE / "forecast-map-settings.json", {"zoom": "8", "layer": []})
        self.assertEqual(f.settings(), {"enabled": False, "zoom": 6, "layer": "precipitation"})

    def test_xml_is_bounded_and_requires_known_layer_style_and_timestamps(self):
        result = f.parse_capabilities(xml(), "precipitation")
        self.assertEqual(result["layer"], "precipitation")
        for raw in (b"<!DOCTYPE x [<!ENTITY y 'test'>]><x/>", b"<error/>", b"<broken", b"x" * (f.XML_LIMIT + 1),
                    xml().replace(b"SIGPRECIPITATIONTYPE", b"EVIL"),
                    xml().replace(b"name=\"time\"", b"name=\"wrong\"")):
            with self.assertRaises(ValueError):
                f.parse_capabilities(raw, "precipitation")

    def test_interval_dimensions_and_future_selection_are_real_and_bounded(self):
        now = 1_800_000_000
        start = now // 3600 * 3600
        times = f.time_dimension(f.iso_time(start) + "/" + f.iso_time(start + 48 * 3600) + "/PT1H")
        value = {"times": times}
        selected = f.future_times(value, now)
        self.assertLessEqual(len(selected), 12)
        self.assertTrue(all(now < stamp <= now + 86400 and stamp in times for stamp in selected))
        self.assertEqual(selected[-1], max(t for t in times if t <= now + 86400))
        for bad in (f.iso_time(start) + "/" + f.iso_time(start + 86400) + "/PT1M", ",".join([f.iso_time(start)] * 501)):
            with self.assertRaises(ValueError):
                f.time_dimension(bad)
        for stamp in (now - 1, now + 86401, True, "next"):
            with self.assertRaises(ValueError):
                f.future_times(value, now, stamp)

    def test_capabilities_reject_expired_reference_and_poisoned_cached_values(self):
        now = int(time.time())
        for value in ({"layer": "evil", "reference": now, "times": [now + 3600]},
                      {"layer": [], "reference": now, "times": [now + 3600]},
                      {"layer": {}, "reference": now, "times": [now + 3600]},
                      {"layer": "clouds", "reference": now - f.MAX_REFERENCE_AGE - 1, "times": [now + 3600]},
                      {"layer": "clouds", "reference": now, "times": [float("nan")]},
                      {"layer": "clouds", "reference": now, "times": [now + 30 * 86400]}):
            with self.assertRaises(ValueError):
                f.validate_capabilities(value, now)

    def test_capabilities_from_another_layer_are_never_used_offline(self):
        f.save_json(f.CACHE / "capabilities-precipitation.json", {"fetched": int(time.time()), "data": capability("temperature")})
        with patch.object(f, "download", side_effect=OSError("offline")):
            with self.assertRaises(OSError):
                f.capabilities("precipitation")

    def test_viewport_is_aligned_to_osm_and_splits_dateline_without_distortion(self):
        parts = f.viewport_parts(45.75, 4.85, 6)
        self.assertEqual(len(parts), 1)
        self.assertAlmostEqual(parts[0]["bbox"][2] - parts[0]["bbox"][0], 2 * f.WORLD_HALF / (64 * 256) * 432)
        for latitude, longitude in ((0, 179.9), (0, -179.9), (85, 180), (-85, -180)):
            parts = f.viewport_parts(latitude, longitude, 3)
            self.assertEqual(len(parts), 2)
            self.assertAlmostEqual(sum(part["width"] for part in parts), 432)
            self.assertAlmostEqual(parts[1]["left"], parts[0]["width"])
            self.assertTrue(all(-f.WORLD_HALF - 0.01 <= x <= f.WORLD_HALF + 0.01 for part in parts for x in part["bbox"]))
        for latitude in (-90, 90):
            with self.assertRaises(ValueError): f.viewport_parts(latitude, 0, 3)
        for lat, lon in ((True, 2), (0, float("nan")), (91, 0), (0, 181), (None, 0)):
            with self.assertRaises(ValueError):
                f.coordinates({"latitude": lat, "longitude": lon})

    def test_png_checks_integrity_dimensions_and_rejects_markup_or_truncation(self):
        self.assertEqual(f.png_size(png()), (432, 240))
        for data in (b"<img src='https://evil.invalid'>", png()[:-1], png() + b"x", png(1025, 1), png()[:50] + b"bad" + png()[53:]):
            with self.assertRaises(ValueError):
                f.png_size(data)

    def test_load_fetches_only_selected_frame_and_navigation_is_lazy_cached(self):
        f.configure({"enabled": True})
        with patch.object(f, "download", side_effect=self.fake_download) as network, patch.object(f.radar, "tile", return_value="file:///base.png"):
            result = f.load(self.city)
            requests = [parse_qs(urlsplit(call.args[0]).query)["REQUEST"][0] for call in network.call_args_list]
            self.assertEqual(requests.count("GetMap"), 1)
            self.assertEqual(requests.count("GetCapabilities"), 1)
            self.assertEqual(sum(bool(frame["images"]) for frame in result["frames"]), 1)
            self.assertTrue(all(p["source"].startswith("file://") for p in result["frames"][0]["images"]))
            self.assertEqual(result["legend"]["width"], 107)
            stamp = result["frames"][1]["time"]
            network.reset_mock()
            next_frame = f.main(["frame", json.dumps({"city": self.city, "time": stamp})])
            self.assertEqual(network.call_count, 1)
            self.assertEqual(next_frame["selected_time"], stamp)
            self.assertEqual(sum(bool(frame["images"]) for frame in next_frame["frames"]), 2)
            network.reset_mock()
            f.main(["frame", json.dumps({"city": self.city, "time": stamp})])
            network.assert_not_called()

    def test_offline_cache_keeps_exact_instant_and_never_borrows_another_city(self):
        f.configure({"enabled": True})
        with patch.object(f, "download", side_effect=self.fake_download), patch.object(f.radar, "tile", return_value="file:///base.png"):
            live = f.load(self.city)
        caps = f.read_json(f.CACHE / "capabilities-precipitation.json", {})
        caps["fetched"] = int(time.time()) - 3600
        f.save_json(f.CACHE / "capabilities-precipitation.json", caps)
        with patch.object(f, "download", side_effect=OSError("offline")), patch.object(f.radar, "tile", return_value=None):
            offline = f.load(self.city)
            self.assertTrue(offline["stale"])
            self.assertEqual(offline["frames"][0]["images"], live["frames"][0]["images"])
            other = f.load({"latitude": 48.85, "longitude": 2.35})
            self.assertFalse(any(frame["images"] for frame in other["frames"]))
            self.assertIn("error", other)

    def test_no_partial_dateline_overlay_after_failed_part(self):
        f.configure({"enabled": True})
        calls = 0
        def network(url, limit):
            nonlocal calls
            if "GetMap" in url:
                calls += 1
                if calls == 2:
                    raise OSError("interrupted")
            return self.fake_download(url, limit)
        with patch.object(f, "download", side_effect=network), patch.object(f.radar, "tile", return_value=None):
            result = f.load({"latitude": 0, "longitude": 179.9})
        self.assertFalse(any(frame["images"] for frame in result["frames"]))
        self.assertIn("error", result)

    def test_requests_pin_reference_projection_and_official_units_legend(self):
        part = f.viewport_parts(45.75, 4.85, 6)[0]
        query = parse_qs(urlsplit(f.map_url("precipitation", 1_800_000_000, 1_800_003_600, part)).query)
        self.assertEqual(query["CRS"], ["EPSG:3857"])
        self.assertEqual(query["STYLES"], ["SIGPRECIPITATIONTYPE"])
        self.assertIn("DIM_REFERENCE_TIME", query)
        self.assertEqual(f.empty_result({"enabled": True, "zoom": 6, "layer": "precipitation"})["unit"], "mm / 1 h")
        self.assertIn("LANG=en", f.legend_url("temperature"))

    def test_redirects_and_foreign_hosts_are_refused_before_network(self):
        for url in ("http://geo.weather.gc.ca/geomet", "https://evil.invalid/geomet", "https://geo.weather.gc.ca.evil.invalid/geomet", "https://geo.weather.gc.ca/other"):
            self.assertFalse(f.allowed_url(url))
            with self.assertRaises(ValueError):
                f.download(url, 100)
            with self.assertRaises(ValueError):
                f.SafeRedirect().redirect_request(None, None, 302, "Found", {}, url)

    def test_network_is_single_flight_and_rate_limited_without_waiting(self):
        f.CACHE.mkdir(parents=True)
        import fcntl
        with (f.CACHE / ".network-lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with self.assertRaises(BlockingIOError):
                f.download(f.WMS_URL, 100)
        f.save_json(f.CACHE / "requests.json", [time.time()] * 24)
        with self.assertRaises(OSError):
            f.download(f.WMS_URL, 100)

    def test_cache_pruning_bounds_disk_and_removes_old_interrupted_writes(self):
        old, newest = f.CACHE / "images/old.png", f.CACHE / "images/new.png"
        f.save_bytes(old, png())
        f.save_bytes(newest, png())
        residue = f.CACHE / ".forecast-interrupted"
        f.save_bytes(residue, b"partial")
        os.utime(residue, (time.time() - 400, time.time() - 400))
        with patch.object(f, "CACHE_BYTES", len(png()) + 1):
            f.prune_cache({newest})
        self.assertTrue(newest.exists())
        self.assertFalse(old.exists())
        self.assertFalse(residue.exists())

    def test_frame_requires_timestamp_instead_of_silently_using_first(self):
        for value in ({"city": self.city}, {"city": self.city, "time": True}, [], {"time": "next"}):
            with self.assertRaises(ValueError):
                f.main(["frame", json.dumps(value)])


if __name__ == "__main__":
    unittest.main()
