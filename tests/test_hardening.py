"""Offline regression gates for transport, persistence and public entry points."""
import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError
from urllib.request import Request
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import network
import storage

spec = importlib.util.spec_from_file_location("hardening_weather", ROOT / "weather.py")
w = importlib.util.module_from_spec(spec)
spec.loader.exec_module(w)
NOW = 1794690000
CITY = {"name": "Paris", "latitude": 48.85, "longitude": 2.35}


def weather_payload():
    return {"timezone": "Europe/Paris", "latitude": CITY["latitude"],
            "current": {"time": NOW, "temperature_2m": 12, "weather_code": 3},
            "hourly": {"time": [NOW // 3600 * 3600], "temperature_2m": [12], "precipitation_probability": [0]},
            "daily": {"time": [datetime.fromtimestamp(NOW, ZoneInfo("Europe/Paris")).date().isoformat()],
                      "temperature_2m_min": [8], "temperature_2m_max": [15]}}


class TransportTests(unittest.TestCase):
    def request_with(self, payload):
        opener = Mock()
        opener.open.return_value = io.BytesIO(payload)
        return patch.object(network, "build_opener", return_value=opener), opener

    def test_only_exact_https_source_hosts_are_allowed(self):
        for url in ("http://api.open-meteo.com/v1/forecast", "https://api.open-meteo.com.evil.invalid/a",
                    "https://api.open-meteo.com:443/a", "https://user:pass@api.open-meteo.com/a",
                    "file:///etc/passwd", "https://127.0.0.1/a", "https://evil.invalid/a"):
            with self.subTest(url=url), patch.object(network, "build_opener") as opener:
                with self.assertRaises(ValueError): network.request(url, {})
                opener.assert_not_called()

    def test_redirects_cannot_leave_the_allowlist_or_downgrade_tls(self):
        handler = network.SafeRedirect()
        for url in ("http://api.open-meteo.com/a", "https://evil.invalid/a", "file:///tmp/test"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                handler.redirect_request(Request(w.WEATHER), None, 302, "redirect", {}, url)

    def test_transport_encodes_query_and_uses_bounded_timeout(self):
        context, opener = self.request_with(b'{"results":[]}')
        with context:
            self.assertEqual(network.request(w.GEO, {"name": "A&B $(noop)"}), {"results": []})
        args, options = opener.open.call_args
        self.assertIn("A%26B+%24%28noop%29", args[0].full_url)
        self.assertEqual(options["timeout"], 8)

    def test_nonfinite_json_and_provider_errors_are_rejected(self):
        for payload in (b'{"value":NaN}', b'{"value":Infinity}', b'{"value":-Infinity}',
                        b'{"value":1e9999}', b'{"error":true}', b'[]', b'not json'):
            context, _ = self.request_with(payload)
            with self.subTest(payload=payload), context, self.assertRaises(ValueError):
                network.request(w.WEATHER, {})

    def test_oversized_response_is_rejected(self):
        context, opener = self.request_with(b' ' * (network.LIMIT + 1))
        with context, self.assertRaisesRegex(ValueError, "too large"):
            network.request(w.WEATHER, {})
        self.assertEqual(opener.open.call_count, 1)

    def test_short_429_retry_happens_once(self):
        opener = Mock()
        error = HTTPError(w.WEATHER, 429, "limited", {"Retry-After": "1"}, None)
        self.addCleanup(error.close)
        opener.open.side_effect = [error, io.BytesIO(b'{"ok":true}')]
        with patch.object(network, "build_opener", return_value=opener), patch.object(network.time, "sleep") as sleep:
            self.assertEqual(network.request(w.WEATHER, {}), {"ok": True})
        self.assertEqual(opener.open.call_count, 2)
        sleep.assert_called_once_with(1)

    def test_long_retry_after_returns_without_sleeping(self):
        opener = Mock()
        error = HTTPError(w.WEATHER, 429, "limited", {"Retry-After": "300"}, None)
        self.addCleanup(error.close)
        opener.open.side_effect = error
        with patch.object(network, "build_opener", return_value=opener), patch.object(network.time, "sleep") as sleep:
            with self.assertRaises(network.NetworkError) as raised:
                network.request(w.WEATHER, {})
        self.assertEqual(raised.exception.retry_after, 300)
        self.assertEqual(opener.open.call_count, 1)
        sleep.assert_not_called()

    def test_retry_limit_and_connection_failure_are_bounded(self):
        for error, count in ((HTTPError(w.WEATHER, 503, "down", {"Retry-After": "0"}, None), 2),
                             (URLError("offline"), 1)):
            if isinstance(error, HTTPError):self.addCleanup(error.close)
            opener = Mock(); opener.open.side_effect = error
            with patch.object(network, "build_opener", return_value=opener), patch.object(network.time, "sleep"):
                with self.assertRaises(network.NetworkError): network.request(w.WEATHER, {})
            self.assertEqual(opener.open.call_count, count)


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.directory = Path(self.temp.name)
        self.path = self.directory / "settings.json"

    def tearDown(self):
        self.temp.cleanup()

    def test_optimistic_commit_refuses_a_concurrent_preference_change(self):
        before, concurrent = {"unit": "C"}, {"unit": "F"}
        storage.save_json(self.path, before)
        storage.save_json(self.path, concurrent)
        backup_before = self.path.with_suffix(".json.bak").read_bytes()
        with self.assertRaisesRegex(OSError, "another instance"):
            storage.commit_settings(self.path, before, {"unit": "C", "cities": []})
        self.assertEqual(storage.read_json(self.path, {}), concurrent)
        self.assertEqual(self.path.with_suffix(".json.bak").read_bytes(), backup_before)

    def test_commits_backup_and_recover_the_last_valid_preferences(self):
        before = {"unit": "F", "cities": [{"name": "Saved"}]}
        storage.save_json(self.path, before)
        storage.commit_settings(self.path, before, {**before, "auto_refresh": False})
        self.path.write_text('{"corrupt":')
        self.assertEqual(storage.read_json(self.path, {}), before)
        storage.commit_settings(self.path, before, {**before, "auto_refresh": True})
        self.assertEqual(storage.read_json(self.path, {})["cities"], before["cities"])

    def test_wrong_preference_shape_recovers_the_valid_backup(self):
        before = {"unit": "F", "cities": [CITY]}
        storage.save_json(self.path.with_suffix(".json.bak"), before)
        for invalid in ([], None, "broken", 12):
            self.path.write_text(json.dumps(invalid))
            self.assertEqual(storage.read_json(self.path, {}), before)

    def test_atomic_disk_failure_keeps_the_existing_file(self):
        before = {"unit": "F"}; storage.save_json(self.path, before)
        for operation in ("replace", "fsync"):
            with self.subTest(operation=operation), patch.object(storage.os, operation, side_effect=OSError("disk full")):
                with self.assertRaises(OSError): storage.save_json(self.path, {"unit": "C"})
            self.assertEqual(json.loads(self.path.read_text()), before)
            self.assertEqual(list(self.directory.glob(".owee-*")), [])

    def test_invalid_json_never_replaces_valid_state(self):
        storage.save_json(self.path, {"unit": "C"})
        with self.assertRaises(ValueError):storage.save_json(self.path, {"bad": float("nan")})
        self.assertEqual(storage.read_json(self.path, {}), {"unit": "C"})
        self.path.write_text('{"bad":NaN}')
        self.assertEqual(storage.read_json(self.path, {"fallback": True}), {"fallback": True})

    def test_state_lock_fails_fast_instead_of_waiting(self):
        path = self.directory / ".test.lock"
        with storage.lock(path):
            with self.assertRaises(BlockingIOError):
                with storage.lock(path):self.fail("exclusive lock acquired twice")

    def test_cache_count_limit_never_deletes_preferences_or_other_state(self):
        keep = {"settings.json": '{"unit":"C"}', "notification-state.json": '{}', "forecast.json": '{}'}
        for name, content in keep.items():(self.directory / name).write_text(content)
        protected = self.directory / "forecast-000.json"
        for i in range(66):
            path = self.directory / (f"forecast-{i:03}.json" if i % 2 == 0 else f"air-{i:03}.json")
            path.write_text('{}');os.utime(path, (100+i, 100+i))
        storage.prune_weather(self.directory, [protected])
        data = list(self.directory.glob("forecast-*.json")) + list(self.directory.glob("air-*.json"))
        self.assertLessEqual(len(data), 64)
        self.assertTrue(protected.exists())
        for name, content in keep.items():self.assertEqual((self.directory / name).read_text(), content)

    def test_cache_byte_limit_removes_only_old_data(self):
        protected = self.directory / "forecast-2.json"
        for i in range(3):
            path = self.directory / f"forecast-{i}.json"
            with path.open("wb") as file:file.truncate(17 * 1024 * 1024)
            os.utime(path, (100+i, 100+i))
        storage.save_json(self.path, {"cities": [CITY]})
        storage.prune_weather(self.directory, [protected])
        self.assertLessEqual(sum(p.stat().st_size for p in self.directory.glob("forecast-*.json")), 32*1024*1024)
        self.assertTrue(protected.exists())
        self.assertEqual(storage.read_json(self.path, {})["cities"], [CITY])


class BackendHardeningTests(unittest.TestCase):
    def test_failed_fetch_never_overwrites_a_newer_cache(self):
        old={"city":CITY,"data":weather_payload(),"updated":NOW-1000,"stale":False}
        old["data"]["current"]["temperature_2m"]=12
        storage.save_json(w.cache_for(CITY),old)
        def competing_fetch(_):
            newer={**old,"data":weather_payload(),"updated":NOW}
            newer["data"]["current"]["temperature_2m"]=20
            storage.save_json(w.cache_for(CITY),newer)
            raise OSError('late failed request')
        with patch.object(w,'forecast',side_effect=competing_fetch):
            result=w.weather_for(CITY,refresh=True,network=True)
        self.assertEqual(result['data']['current']['temperature_2m'],20)
        self.assertEqual(storage.read_json(w.cache_for(CITY),{})['updated'],NOW)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.state = Path(self.temp.name)
        self.context = patch.multiple(w, STATE=self.state, MIN_REFRESH_SECONDS=60)
        self.context.start()
        self.clock = patch.object(w.time, "time", return_value=NOW)
        self.mock_clock = self.clock.start()

    def tearDown(self):
        self.clock.stop(); self.context.stop(); self.temp.cleanup()

    def test_coordinates_search_does_not_contact_geocoding(self):
        with patch.object(w, "request") as request:
            result = w.search(" -33.87000, +151.21000 ")
        request.assert_not_called()
        self.assertEqual((result["results"][0]["latitude"], result["results"][0]["longitude"]), (-33.87,151.21))
        for query in ("91,0", "0,-181", "-90.1,2"):
            with patch.object(w, "request") as request, self.assertRaises(ValueError):w.search(query)
            request.assert_not_called()

    def test_coordinates_reject_boolean_or_nonfinite_values(self):
        for change in ({"latitude": True}, {"longitude": False}, {"latitude": float("nan")}, {"longitude": float("inf")}):
            with self.subTest(change=change), self.assertRaises(ValueError):w.location({**CITY, **change})

    def test_primary_forecast_load_does_not_wait_for_air_or_pollen(self):
        with patch.object(w, "request", return_value=weather_payload()) as request:
            result = w.main(["load"])
        self.assertEqual(result["data"]["current"]["temperature_2m"], 12)
        self.assertFalse(result["stale"])
        self.assertEqual(request.call_count, 1)
        self.assertEqual(request.call_args.args[0], w.WEATHER)
        self.assertEqual(request.call_args.args[1]["timeformat"], "unixtime")
        self.assertEqual(request.call_args.args[1]["forecast_days"], 11)
        self.assertIn("capabilities", result["data"])

    def test_repeated_manual_refresh_uses_production_sixty_second_guard(self):
        with patch.object(w, "request", return_value=weather_payload()) as request:
            first = w.weather_for(CITY, refresh=True, network=True)
            second = w.weather_for(CITY, refresh=True, network=True)
            self.assertEqual(request.call_count, 1)
            self.assertEqual(first["updated"], second["updated"])
            self.mock_clock.return_value = NOW + 61
            w.weather_for(CITY, refresh=True, network=True)
            self.assertEqual(request.call_count, 2)

    def test_air_enrichment_preserves_zero_and_missing_pollen_with_one_hour_ttl(self):
        air = {"timezone": "Europe/Paris", "current": {"time": NOW, "european_aqi":24, "pm2_5":0, "grass_pollen":None}}
        with patch.object(w, "request", return_value=air) as request:
            first = w.enrich(CITY)
            again = w.enrich(CITY)
            self.assertEqual(request.call_count, 1)
            self.assertEqual(first["air"]["pm2_5"], 0)
            self.assertEqual(again["capabilities"]["pollen"]["status"], "unavailable")
            self.assertFalse(again["stale"])
            self.mock_clock.return_value = NOW + 3601
            request.side_effect = OSError("offline")
            cached = w.enrich(CITY)
            self.assertTrue(cached["stale"])
            self.assertEqual(cached["air"]["european_aqi"], 24)

    def test_failed_optional_enrichment_never_removes_cached_core_weather(self):
        with patch.object(w, "request", return_value=weather_payload()):w.weather_for(CITY, refresh=True, network=True)
        with patch.object(w, "request", side_effect=OSError("offline")):
            missing = w.enrich(CITY)
            weather = w.weather_for(CITY)
        self.assertEqual(missing["capabilities"]["pollen"]["status"], "unavailable")
        self.assertEqual(weather["data"]["current"]["temperature_2m"], 12)
        self.assertFalse(weather["stale"])

    def test_corrupt_optional_air_cache_does_not_break_a_fresh_forecast(self):
        storage.save_json(w.air_path(CITY), {"city_key": w.city_key(CITY), "updated": NOW, "air": []})
        with patch.object(w, "request", return_value=weather_payload()):
            result = w.forecast(CITY)
        self.assertEqual(result["data"]["current"]["temperature_2m"], 12)

    def test_corrupt_embedded_air_does_not_discard_an_offline_weather_cache(self):
        with patch.object(w, "request", return_value=weather_payload()):result = w.forecast(CITY)
        result["data"]["air"] = []
        storage.save_json(w.cache_for(CITY), result)
        with patch.object(w, "request") as request:cached = w.weather_for(CITY)
        request.assert_not_called()
        self.assertEqual(cached["data"]["current"]["temperature_2m"], 12)

    def test_provider_retry_after_is_shared_without_another_http_attempt(self):
        with patch.object(w.network, "request", side_effect=network.NetworkError("limited", 120)) as request:
            with self.assertRaises(network.NetworkError):w.request(w.WEATHER, {})
            with self.assertRaisesRegex(network.NetworkError, "cooling down"):w.request(w.WEATHER, {})
        self.assertEqual(request.call_count, 1)
        self.assertEqual(storage.read_json(self.state / ".weather-backoff.json", {})["api.open-meteo.com"], NOW + 120)


if __name__ == "__main__":
    unittest.main()
