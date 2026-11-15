"""Regression cases for normalized world time and malformed provider payloads."""
import json
import sys
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import weather_data as adapter


def epoch(value):
    return int(datetime.fromisoformat(value).timestamp())


def fixture(zone="Europe/Paris", times=None):
    times = times or [epoch("2026-11-15T00:00:00+00:00") + h * 3600 for h in range(24)]
    local = datetime.fromtimestamp(times[0], ZoneInfo(zone))
    count = len(times)
    return {
        "timezone": zone, "latitude": 48.85,
        "current": {"time": times[0], "temperature_2m": 12, "weather_code": 3,
                    "is_day": 1, "relative_humidity_2m": 75, "interval": 900},
        "hourly": {"time": times, "temperature_2m": [12] * count,
                   "precipitation_probability": [70] * count,
                   "weather_code": [61] * count, "is_day": [1] * count},
        "daily": {"time": [local.date().isoformat()], "temperature_2m_min": [4],
                  "temperature_2m_max": [15], "sunrise": [local.date().isoformat() + "T07:30"],
                  "sunset": [local.date().isoformat() + "T17:20"],
                  "daylight_duration": [35400], "uv_index_max": [2]},
    }


class WeatherDataTests(unittest.TestCase):
    def test_numeric_times_preserve_utc_and_city_clock(self):
        raw = fixture("Asia/Tokyo")
        data = adapter.normalize_weather(raw)
        self.assertEqual(data["current"]["time"], "2026-11-15T09:00")
        self.assertEqual(data["current"]["time_utc"], raw["current"]["time"])
        self.assertEqual(data["hourly"]["time_utc"], raw["hourly"]["time"])
        self.assertEqual(data["hourly"]["rain_intervals"][0]["start_local"], "2026-11-15T08:00")
        self.assertEqual(data["capabilities"]["time"]["precision"], "utc")

    def test_legacy_fixture_remains_usable(self):
        raw = {"timezone": "Europe/Paris", "current": {"temperature_2m": 12, "time": "2026-11-12T10:15"},
               "hourly": {"time": ["2026-11-12T10:00"]}, "daily": {"time": ["2026-11-12"]}}
        data = adapter.normalize_weather(raw)
        self.assertEqual(data["current"]["temperature_2m"], 12)
        self.assertEqual(data["hourly"]["precipitation_probability"], [None])
        self.assertEqual(data["daily"]["solar_state"], ["unavailable"])

    def test_repeated_new_york_hour_keeps_both_real_intervals(self):
        times = [epoch("2026-11-01T05:00:00+00:00"), epoch("2026-11-01T06:00:00+00:00"),
                 epoch("2026-11-01T07:00:00+00:00")]
        data = adapter.normalize_weather(fixture("America/New_York", times))
        self.assertEqual(data["hourly"]["time"][:2], ["2026-11-01T01:00"] * 2)
        intervals = data["hourly"]["rain_intervals"]
        self.assertEqual([row["hour"] for row in intervals], [0, 1, 1])
        self.assertEqual([(row["start_offset"], row["end_offset"]) for row in intervals],
                         [(-14400, -14400), (-14400, -18000), (-18000, -18000)])
        self.assertTrue(all(row["end_utc"] - row["start_utc"] == 3600 for row in intervals))

    def test_spring_clock_gap_is_not_filled_with_a_fictional_instant(self):
        times = [epoch("2026-03-08T06:00:00+00:00"), epoch("2026-03-08T07:00:00+00:00"),
                 epoch("2026-03-08T08:00:00+00:00")]
        data = adapter.normalize_weather(fixture("America/New_York", times))
        self.assertEqual(data["hourly"]["time"], ["2026-03-08T01:00", "2026-03-08T03:00", "2026-03-08T04:00"])
        self.assertEqual([row["hour"] for row in data["hourly"]["rain_intervals"]], [0, 1, 3])

    def test_legacy_ambiguous_or_missing_hour_never_guesses_a_fold(self):
        for label in ("2026-11-01T01:30", "2026-03-08T02:30"):
            raw = fixture("America/New_York", [epoch("2026-11-15T00:00:00+00:00")])
            raw["current"]["time"] = label
            raw["hourly"]["time"] = [label]
            data = adapter.normalize_weather(raw)
            self.assertEqual(data["current"]["time"], label)
            self.assertIsNone(data["current"]["time_utc"])
            self.assertEqual(data["hourly"]["rain_intervals"], [])
            self.assertEqual(data["capabilities"]["time"]["precision"], "legacy_partial")

    def test_explicit_offset_disambiguates_legacy_clock(self):
        raw = fixture("America/New_York")
        raw["current"]["time"] = "2026-11-01T01:30:00-05:00"
        self.assertEqual(adapter.normalize_weather(raw)["current"]["time_utc"], epoch("2026-11-01T06:30:00+00:00"))

    def test_fractional_timezones_keep_their_actual_offsets(self):
        for zone, label, offset in (("Asia/Kathmandu", "2026-11-15T05:45", 20700),
                                    ("Australia/Adelaide", "2026-11-15T10:30", 37800)):
            data = adapter.normalize_weather(fixture(zone))
            self.assertEqual(data["current"]["time"], label)
            self.assertEqual(data["hourly"]["rain_intervals"][0]["end_offset"], offset)

    def test_midnight_interval_belongs_to_previous_month_or_year(self):
        for instant, expected in (("2026-01-01T00:00:00+00:00", "2025-12-31"),
                                  ("2028-03-01T00:00:00+00:00", "2028-02-29")):
            data = adapter.normalize_weather(fixture("UTC", [epoch(instant)]))
            row = data["hourly"]["rain_intervals"][0]
            self.assertEqual((row["date"], row["hour"]), (expected, 23))

    def test_solar_events_are_null_in_polar_day_and_night(self):
        for duration, state in ((0, "polar_night"), (86400, "polar_day")):
            raw = fixture("Etc/GMT")
            raw["latitude"] = 90
            raw["daily"].update(daylight_duration=[duration], sunrise=["2026-11-15T00:00"], sunset=["2026-11-15T00:00"])
            daily = adapter.normalize_weather(raw)["daily"]
            self.assertEqual(daily["solar_state"], [state])
            self.assertEqual(daily["sunrise"], [None])
            self.assertEqual(daily["sunset_utc"], [None])

    def test_midnight_labels_alone_do_not_claim_a_polar_state(self):
        raw = fixture()
        raw["daily"].update(sunrise=["2026-11-15T00:00"], sunset=["2026-11-15T00:00"], daylight_duration=[None])
        daily = adapter.normalize_weather(raw)["daily"]
        self.assertEqual(daily["solar_state"], ["unavailable"])
        self.assertEqual(daily["sunrise"], [None])

    def test_utc_solar_events_and_daily_dates_use_the_city_timezone(self):
        raw = fixture("Asia/Tokyo")
        raw["daily"].update(time=[epoch("2026-11-14T15:00:00+00:00")],
                            sunrise=[epoch("2026-11-14T21:00:00+00:00")],
                            sunset=[epoch("2026-11-15T08:00:00+00:00")])
        daily = adapter.normalize_weather(raw)["daily"]
        self.assertEqual(daily["time"], ["2026-11-15"])
        self.assertEqual(daily["sunrise"], ["2026-11-15T06:00"])
        self.assertEqual(daily["solar_state"], ["normal"])

    def test_invalid_required_readings_and_timestamps_reject(self):
        for field, values in (("temperature_2m", (True, "12", None, float("nan"), float("inf"), 10**1000, -151)),
                              ("time", (True, {}, "bad", float("nan")))):
            for value in values:
                raw = fixture(); raw["current"][field] = value
                with self.subTest(field=field, value=repr(value)[:30]), self.assertRaises(ValueError):
                    adapter.normalize_weather(raw)

    def test_invalid_zone_axes_and_dates_reject(self):
        for mutate in (lambda r:r.update(timezone="Not/A_Zone"), lambda r:r["hourly"].update(time={}),
                       lambda r:r["daily"].update(time=["2026-02-30"]), lambda r:r.update(current=[]),
                       lambda r:r["hourly"].update(time=[True]), lambda r:r["daily"].update(time=["9999-01-01"])):
            raw = fixture(); mutate(raw)
            with self.assertRaises(ValueError): adapter.normalize_weather(raw)

    def test_nonmonotonic_numeric_axis_rejects(self):
        raw = fixture(); raw["hourly"]["time"][1] = raw["hourly"]["time"][0]
        with self.assertRaises(ValueError): adapter.normalize_weather(raw)

    def test_normalized_cache_roundtrip_preserves_dst_instants(self):
        times = [epoch("2026-11-01T05:00:00+00:00"), epoch("2026-11-01T06:00:00+00:00"),
                 epoch("2026-11-01T07:00:00+00:00")]
        once = adapter.normalize_weather(fixture("America/New_York", times))
        twice = adapter.normalize_weather(json.loads(json.dumps(once)))
        self.assertEqual(twice["hourly"]["time_utc"], times)
        self.assertEqual(twice["hourly"]["rain_intervals"], once["hourly"]["rain_intervals"])
        self.assertEqual(twice["current"]["time_utc"], once["current"]["time_utc"])

    def test_normalized_cache_roundtrip_preserves_polar_state_and_utc_sunrise(self):
        raw = fixture("Etc/GMT"); raw["latitude"] = 90
        raw["daily"].update(daylight_duration=[0], sunrise=["2026-11-15T00:00"], sunset=["2026-11-15T00:00"])
        twice = adapter.normalize_weather(adapter.normalize_weather(raw))
        self.assertEqual(twice["daily"]["solar_state"], ["polar_night"])
        raw = fixture("America/New_York")
        raw["daily"].update(time=["2026-11-01"], sunrise=[epoch("2026-11-01T05:30:00+00:00")],
                            sunset=[epoch("2026-11-01T07:30:00+00:00")])
        once = adapter.normalize_weather(raw)
        self.assertEqual(adapter.normalize_weather(once)["daily"]["sunrise_utc"], once["daily"]["sunrise_utc"])

    def test_corrupted_cached_utc_axis_is_not_guessed_from_labels(self):
        raw = adapter.normalize_weather(fixture())
        raw["hourly"]["time_utc"] = [1]
        with self.assertRaises(ValueError): adapter.normalize_weather(raw)

    def test_optional_bad_fields_do_not_remove_the_weather(self):
        raw = fixture()
        raw["current"].update(relative_humidity_2m=True, wind_speed_10m=float("nan"), weather_code={"code":3})
        raw["hourly"].update(temperature_2m={"wrong":"shape"}, precipitation_probability=[0, None, False, float("inf"), 101])
        data = adapter.normalize_weather(raw)
        self.assertEqual(data["current"]["temperature_2m"], 12)
        self.assertIsNone(data["current"]["relative_humidity_2m"])
        self.assertIsNone(data["current"]["weather_code"])
        self.assertEqual(data["hourly"]["precipitation_probability"][:5], [0,None,None,None,None])
        self.assertEqual(data["capabilities"]["hourly_rain"]["status"], "partial")
        json.dumps(data, allow_nan=False)

    def test_optional_arrays_never_misalign_with_their_time_axis(self):
        raw = fixture(); raw["hourly"]["visibility"] = [10] * 25
        self.assertEqual(adapter.normalize_weather(raw)["hourly"]["visibility"], [None] * 24)
        raw["hourly"]["visibility"] = [10]
        self.assertEqual(adapter.normalize_weather(raw)["hourly"]["visibility"], [10] + [None] * 23)

    def test_bounds_limit_arrays_and_trim_daily_to_ten(self):
        raw = fixture()
        raw["hourly"]["time"] *= 22
        with self.assertRaises(ValueError): adapter.normalize_weather(raw)
        raw = fixture(); raw["hourly"]["visibility"] = [0] * 501
        with self.assertRaises(ValueError): adapter.normalize_weather(raw)
        raw = fixture()
        raw["daily"] = {"time": [(datetime(2026,11,15)+timedelta(days=i)).date().isoformat() for i in range(11)]}
        data = adapter.normalize_weather(raw)
        self.assertTrue(all(len(values) == 10 for values in data["daily"].values()))

    def test_air_partial_zero_and_absent_are_distinct(self):
        data = adapter.normalize_air({"current":{"european_aqi":0, "pm2_5":3, "grass_pollen":0}})
        self.assertEqual(data["current"]["grass_pollen"], 0)
        self.assertEqual(data["capabilities"]["air"]["status"], "available")
        self.assertEqual(data["capabilities"]["pollen"]["status"], "partial")
        absent = adapter.normalize_air({"current":{"european_aqi":24}})
        self.assertEqual(absent["capabilities"]["pollen"]["status"], "unavailable")
        self.assertNotEqual(absent["capabilities"]["pollen"]["status"], "unsupported")

    def test_air_bad_fields_do_not_create_zero_or_nan(self):
        data = adapter.normalize_air({"current":{"european_aqi":True, "pm2_5":float("nan"), "grass_pollen":-1, "birch_pollen":10**1000}})
        self.assertTrue(all(value is None for value in data["current"].values()))
        json.dumps(data, allow_nan=False)
        with self.assertRaises(ValueError):adapter.normalize_air({"current":[]})


if __name__ == "__main__":
    unittest.main()
