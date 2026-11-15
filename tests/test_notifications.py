import copy
import fcntl
import importlib.util
import json
import subprocess
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

spec = importlib.util.spec_from_file_location('weather_notifications', Path(__file__).resolve().parents[1] / 'notifications.py')
n = importlib.util.module_from_spec(spec)
spec.loader.exec_module(n)
NOW = datetime(2026, 11, 13, 9, 15, tzinfo=timezone.utc)


def fixture(now=NOW, zone='Europe/Paris'):
    local = now.astimezone(ZoneInfo(zone))
    hour = local.replace(minute=0, second=0, microsecond=0)
    return {
        'city': {'name': 'Lyon', 'latitude': 45.75, 'longitude': 4.85},
        'updated': now.timestamp(), 'stale': False, 'unit': 'C',
        'data': {
            'timezone': zone,
            'current': {'time': local.replace(tzinfo=None).isoformat(timespec='minutes'),
                        'temperature_2m': 12, 'wind_speed_10m': 55, 'is_day': 1},
            'hourly': {
                'time': [(hour + timedelta(hours=i)).replace(tzinfo=None).isoformat(timespec='minutes') for i in range(8)],
                'precipitation_probability': [0, 70, 90, 0, 0, 0, 0, 0],
            },
            'daily': {'time': [local.date().isoformat()], 'uv_index_max': [7],
                      'temperature_2m_min': [8], 'temperature_2m_max': [16]},
        },
    }


def config(**changes):
    return {**n.DEFAULTS, 'enabled': True, 'quiet_enabled': False, **changes}


class NotificationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.state = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_settings_are_strict_and_bounded(self):
        self.assertFalse(n.normalise_settings({'enabled': 'true'})['enabled'])
        bounded = n.normalise_settings({'rain_hours': 500, 'rain_probability': float('nan'),
                                        'daily_time': '25:00', 'wind_kmh': -1,
                                        'cooldown_minutes': 0, 'unknown': '<img>'})
        self.assertEqual(bounded['rain_hours'], 6)
        self.assertEqual(bounded['rain_probability'], 60)
        self.assertEqual(bounded['daily_time'], '08:00')
        self.assertEqual(bounded['wind_kmh'], 5)
        self.assertEqual(bounded['cooldown_minutes'], 15)
        self.assertNotIn('unknown', bounded)
        self.assertEqual(n.normalise_settings([]), n.DEFAULTS)
        self.assertEqual(n.normalise_settings({'wind_kmh': 10 ** 1000})['wind_kmh'], 50)

    @patch.object(n, '_send')
    def test_disabled_by_default_has_no_side_effect(self, send):
        self.assertEqual(n.dispatch(fixture(), {}, self.state, NOW), {'sent': 0})
        send.assert_not_called()
        self.assertEqual(list(self.state.iterdir()), [])

    def test_thresholds_each_rule_and_toggle(self):
        result = fixture()
        rules = n.evaluate(result, config(), NOW)
        self.assertEqual([item['kind'] for item in rules], ['rain', 'wind', 'uv'])
        self.assertEqual([item['title'] for item in rules],
                         ['Precipitation in Lyon', 'Strong wind in Lyon', 'UV index in Lyon'])
        self.assertIn('city local time', rules[0]['body'])
        self.assertIn('Forecast maximum today', rules[2]['body'])
        self.assertIn('70 %', rules[0]['body'])
        self.assertEqual(n.evaluate(result, config(rain_probability=95, wind_kmh=60, uv_index=8), NOW), [])
        self.assertEqual(n.evaluate(result, config(rain=False, wind=False, uv=False), NOW), [])

    def test_expired_rain_interval_never_triggers_upcoming_alert(self):
        result=fixture()
        result['data']['hourly']['precipitation_probability']=[90,0,0,0,0,0,0,0]
        self.assertEqual(n.evaluate(result,config(wind=False,uv=False),NOW),[])

    def test_precipitation_window_and_foreign_city_timezone(self):
        result = fixture(zone='America/New_York')
        rules = n.evaluate(result, config(wind=False, uv=False), NOW)
        self.assertEqual(len(rules), 1)
        self.assertIn('05:00', rules[0]['body'])
        result['data']['hourly']['precipitation_probability'] = [0, 0, 0, 0, 90, 0, 0, 0]
        self.assertEqual(n.evaluate(result, config(wind=False, uv=False, rain_hours=3), NOW), [])
        self.assertEqual(len(n.evaluate(result, config(wind=False, uv=False, rain_hours=5), NOW)), 1)

    def test_stale_or_malformed_forecasts_never_notify(self):
        mutations = [
            lambda r: r.update(stale=True),
            lambda r: r.update(error='offline'),
            lambda r: r.update(updated=NOW.timestamp() - 1801),
            lambda r: r.update(updated=NOW.timestamp() + 61),
            lambda r: r.update(updated=float('nan')),
            lambda r: r['data']['current'].update(time='2020-01-01T01:00'),
            lambda r: r['data'].update(timezone='https://bad.invalid'),
            lambda r: r['city'].update(latitude=float('nan')),
            lambda r: r['city'].update(name=[]),
            lambda r: r.update(data=[]),
        ]
        for mutate in mutations:
            with self.subTest(mutate=mutate):
                result = fixture()
                mutate(result)
                self.assertEqual(n.evaluate(result, config(), NOW), [])
        self.assertEqual(n.evaluate([], config(), NOW), [])

    def test_missing_and_nonfinite_rule_values_are_ignored(self):
        result = fixture()
        result['data']['current']['wind_speed_10m'] = float('inf')
        result['data']['daily']['uv_index_max'] = [True]
        result['data']['hourly']['precipitation_probability'] = [None, '90', float('nan')]
        self.assertEqual(n.evaluate(result, config(), NOW), [])
        result['data']['hourly']['time'] = ['invalid']
        result['data']['daily'] = []
        self.assertEqual(n.evaluate(result, config(daily=True, daily_time=NOW.astimezone().strftime('%H:%M')), NOW)[0]['kind'], 'daily')

    def test_quiet_hours_cross_midnight_and_same_day(self):
        local = NOW.astimezone()
        before = (local - timedelta(hours=1)).strftime('%H:%M')
        after = (local + timedelta(hours=1)).strftime('%H:%M')
        self.assertEqual(n.evaluate(fixture(), config(quiet_enabled=True, quiet_start=before, quiet_end=after), NOW), [])
        night = local.replace(hour=23, minute=0)
        self.assertEqual(n.evaluate(fixture(night), config(quiet_enabled=True), night), [])
        morning = local.replace(hour=6, minute=59)
        self.assertEqual(n.evaluate(fixture(morning), config(quiet_enabled=True), morning), [])
        end = local.replace(hour=7, minute=0)
        self.assertTrue(n.evaluate(fixture(end), config(quiet_enabled=True), end))
        self.assertTrue(n.evaluate(fixture(), config(quiet_enabled=True, quiet_start='00:00', quiet_end='00:00'), NOW))

    def test_daily_bulletin_uses_desktop_schedule_and_fahrenheit(self):
        local = NOW.astimezone()
        minute = local.hour * 60 + local.minute
        # Build a scheduled time 15 minutes before the chosen desktop time.
        schedule = f'{(minute - 15) // 60:02d}:{(minute - 15) % 60:02d}'
        result = fixture(zone='America/New_York')
        result['unit'] = 'F'
        rules = n.evaluate(result, config(rain=False, wind=False, uv=False, daily=True, daily_time=schedule), NOW)
        self.assertEqual([item['kind'] for item in rules], ['daily'])
        self.assertIn('54°F', rules[0]['body'])
        self.assertIn('46°F', rules[0]['body'])
        later = NOW + timedelta(hours=1)
        self.assertEqual(n.evaluate(fixture(later), config(rain=False, wind=False, uv=False, daily=True, daily_time=schedule), later), [])

    def test_uv_matches_city_date_instead_of_first_daily_row(self):
        result = fixture()
        result['data']['daily']['time'].insert(0, '2026-11-12')
        result['data']['daily']['uv_index_max'] = [12, 1]
        self.assertEqual(n.evaluate(result, config(rain=False, wind=False), NOW), [])

    @patch.object(n, '_send')
    def test_dedup_survives_new_dispatch_and_cooldown_is_per_type(self, send):
        settings = config(rain=False, uv=False)
        self.assertEqual(n.dispatch(fixture(), settings, self.state, NOW)['sent'], 1)
        self.assertEqual(n.dispatch(fixture(), settings, self.state, NOW)['sent'], 0)
        later = NOW + timedelta(minutes=10)
        self.assertEqual(n.dispatch(fixture(later), settings, self.state, later)['sent'], 0)
        later = NOW + timedelta(minutes=181)
        self.assertEqual(n.dispatch(fixture(later), settings, self.state, later)['sent'], 1)
        self.assertEqual(send.call_count, 2)
        self.assertTrue((self.state / 'notification-state.json').is_file())

    @patch.object(n, '_send')
    def test_independent_city_and_daily_dedup(self, send):
        settings = config(rain=False, wind=False)
        self.assertEqual(n.dispatch(fixture(), settings, self.state, NOW)['sent'], 1)
        later = NOW + timedelta(hours=4)
        self.assertEqual(n.dispatch(fixture(later), settings, self.state, later)['sent'], 0)
        other = fixture(later)
        other['city'] = {'name': 'Paris', 'latitude': 48.85, 'longitude': 2.35}
        self.assertEqual(n.dispatch(other, settings, self.state, later)['sent'], 1)
        tomorrow = NOW + timedelta(days=1)
        self.assertEqual(n.dispatch(fixture(tomorrow), settings, self.state, tomorrow)['sent'], 1)

    @patch.object(n, '_send', side_effect=OSError('no daemon'))
    def test_failed_send_is_reported_and_not_marked_sent(self, send):
        status = n.dispatch(fixture(), config(rain=False, uv=False), self.state, NOW)
        self.assertEqual(status['sent'], 0)
        self.assertIn('error', status)
        self.assertFalse((self.state / 'notification-state.json').exists())
        self.assertIn('error', n.send_test())

    @patch.object(n, '_send')
    def test_concurrent_dispatch_does_not_duplicate(self, send):
        with (self.state / 'notifications.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            self.assertEqual(n.dispatch(fixture(), config(), self.state, NOW)['sent'], 0)
        send.assert_not_called()

    @patch.object(n.subprocess, 'run')
    def test_notification_sinks_escape_markup_and_use_argv(self, run):
        malicious = '<img src="https://evil.invalid/x"> & $(touch /tmp/pwn)'
        result = fixture()
        result['city']['name'] = malicious
        n.dispatch(result, config(rain=False, uv=False), self.state, NOW)
        command = run.call_args.args[0]
        self.assertEqual(command[0], 'notify-send')
        self.assertIn('--', command)
        self.assertNotIn('<img', command[-2])
        self.assertIn('&lt;img', command[-2])
        self.assertIn('$(touch /tmp/pwn)', command[-2])
        self.assertNotIn('shell', run.call_args.kwargs)
        self.assertEqual(run.call_args.kwargs['timeout'], 3)
        n.send_test({'name': malicious})
        self.assertIn('&lt;img', run.call_args.args[0][-1])
        self.assertNotIn('<img', run.call_args.args[0][-1])

    @patch.object(n.subprocess, 'run', side_effect=subprocess.TimeoutExpired('notify-send', 3))
    def test_send_test_timeout_is_bounded(self, run):
        self.assertEqual(n.send_test()['sent'], 0)

    @patch.object(n, '_send')
    def test_corrupt_or_large_dedup_state_recovers(self, send):
        state = self.state / 'notification-state.json'
        for content in ('[]', 'not json', 'x' * (n.STATE_LIMIT + 1)):
            state.write_text(content)
            self.assertEqual(n.dispatch(fixture(), config(rain=False, uv=False), self.state, NOW)['sent'], 1)
            self.assertIsInstance(json.loads(state.read_text()), dict)


if __name__ == '__main__':
    unittest.main()
