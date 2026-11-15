"""Production regressions for freshness, delivery reservations and diagnostics."""
import contextlib
import importlib.util
import io
import json
from datetime import datetime, timedelta
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import notifications as n
import storage

spec = importlib.util.spec_from_file_location('production_weather', ROOT / 'weather.py')
w = importlib.util.module_from_spec(spec)
spec.loader.exec_module(w)
NOW = datetime(2026, 11, 16, 0, 10, tzinfo=ZoneInfo('Europe/Paris'))
EPOCH = int(NOW.timestamp())
CITY = {'name': 'Lyon', 'latitude': 45.75, 'longitude': 4.85}


def payload(observed=EPOCH):
    return {'timezone': 'Europe/Paris',
            'current': {'time': observed, 'temperature_2m': 12, 'wind_speed_10m': 80},
            'hourly': {'time': [EPOCH + 3600]},
            'daily': {'time': [NOW.date().isoformat()],
                      'temperature_2m_min': [8], 'temperature_2m_max': [15]}}


def result(observed=EPOCH, updated=EPOCH):
    return {'city': CITY, 'data': payload(observed), 'updated': updated, 'stale': False}


def rules(**changes):
    return {**n.DEFAULTS, 'enabled': True, 'quiet_enabled': False,
            'rain': False, 'uv': False, **changes}


class ProductionBackendTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.state = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)
        self.addCleanup(patch.stopall)
        patch.object(w, 'STATE', self.state).start()
        patch.object(w.time, 'time', return_value=EPOCH).start()
        patch.object(n, '_local_now', return_value=NOW).start()

    def test_old_observation_cannot_be_fresh_after_a_new_download(self):
        with patch.object(w, 'request', return_value=payload(EPOCH - 5401)):
            self.assertTrue(w.forecast(CITY)['stale'])

    def test_future_observation_cannot_be_fresh_after_a_new_download(self):
        with patch.object(w, 'request', return_value=payload(EPOCH + 301)):
            self.assertTrue(w.forecast(CITY)['stale'])

    def test_freshness_observation_boundaries_remain_inclusive(self):
        for observed in (EPOCH - 5400, EPOCH, EPOCH + 300):
            with self.subTest(observed=observed), patch.object(w, 'request', return_value=payload(observed)):
                self.assertFalse(w.forecast(CITY)['stale'])

    def test_cache_freshness_checks_observation_and_download_age(self):
        for observed, updated, stale in ((EPOCH - 5401, EPOCH, True),
                                         (EPOCH + 301, EPOCH, True),
                                         (EPOCH, EPOCH - 1801, True),
                                         (EPOCH - 5400, EPOCH - 1800, False)):
            with self.subTest(observed=observed, updated=updated):
                storage.save_json(w.cache_for(CITY), result(observed, updated))
                self.assertEqual(w.cached_forecast(CITY)['stale'], stale)

    def test_stale_incoming_response_preserves_a_newer_valid_cache(self):
        cached = result(EPOCH, EPOCH - 120)
        storage.save_json(w.cache_for(CITY), cached)
        original = w.cache_for(CITY).read_bytes()
        with patch.object(w, 'request', return_value=payload(EPOCH - 7200)):
            received = w.weather_for(CITY, refresh=True, network=True)
        self.assertEqual(received['data']['current']['time_utc'], EPOCH)
        self.assertFalse(received['stale'])
        self.assertEqual(w.cache_for(CITY).read_bytes(), original)

    def test_future_incoming_response_cannot_replace_a_fresh_valid_cache(self):
        storage.save_json(w.cache_for(CITY), result(EPOCH, EPOCH - 120))
        original = w.cache_for(CITY).read_bytes()
        with patch.object(w, 'request', return_value=payload(EPOCH + 301)):
            received = w.weather_for(CITY, refresh=True, network=True)
        self.assertEqual(received['data']['current']['time_utc'], EPOCH)
        self.assertEqual(w.cache_for(CITY).read_bytes(), original)

    def test_daily_window_crosses_midnight_and_uses_occurrence_date(self):
        settings = rules(wind=False, daily=True, daily_time='23:30')
        candidates = n.evaluate(result(), settings, NOW)
        self.assertEqual([item['kind'] for item in candidates], ['daily'])
        self.assertEqual(candidates[0]['signature'], '2026-11-15')

    def test_daily_window_expires_at_sixty_real_minutes(self):
        later = NOW.replace(minute=30)
        with patch.object(n, '_local_now', return_value=later):
            self.assertEqual(n.evaluate(result(int(later.timestamp()), int(later.timestamp())),
                                        rules(wind=False, daily=True, daily_time='23:30'), later), [])

    def test_midnight_does_not_duplicate_a_daily_bulletin(self):
        before = NOW - timedelta(minutes=20)
        settings = rules(wind=False, daily=True, daily_time='23:30')
        with patch.object(n, '_send') as send:
            with patch.object(n, '_local_now', return_value=before):
                self.assertEqual(n.dispatch(result(int(before.timestamp()), int(before.timestamp())),
                                            settings, self.state, before)['sent'], 1)
            self.assertEqual(n.dispatch(result(), settings, self.state, NOW)['sent'], 0)
        self.assertEqual(send.call_count, 1)

    def test_disk_failure_before_reservation_prevents_delivery(self):
        with patch.object(n, '_save_records', side_effect=OSError('disk full')), \
                patch.object(n, '_send') as send:
            status = n.dispatch(result(), rules(), self.state, NOW)
        self.assertEqual(status['sent'], 0)
        self.assertIn('history', status['error'])
        send.assert_not_called()

    def test_reservation_is_fsynced_before_delivery(self):
        events = []
        real_fsync = n.os.fsync
        def fsync(fd):
            real_fsync(fd)
            events.append('fsync')
        def send(*args):
            self.assertTrue((self.state / 'notification-state.json').is_file())
            self.assertGreaterEqual(events.count('fsync'), 2)
            events.append('send')
        with patch.object(n.os, 'fsync', side_effect=fsync), patch.object(n, '_send', side_effect=send):
            self.assertEqual(n.dispatch(result(), rules(), self.state, NOW)['sent'], 1)
        self.assertEqual(events[-1], 'send')

    def test_failed_delivery_retains_reservation_and_prevents_another_attempt(self):
        with patch.object(n, '_send', side_effect=OSError('no daemon')) as send:
            first = n.dispatch(result(), rules(), self.state, NOW)
            second = n.dispatch(result(), rules(), self.state, NOW)
        self.assertEqual(first['sent'], 0)
        self.assertIn('error', first)
        self.assertEqual(second['sent'], 0)
        self.assertEqual(send.call_count, 1)

    def test_internal_forecast_failure_emits_sanitized_stderr_and_preserves_stdout(self):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err), \
                patch.object(w, 'forecast', side_effect=RuntimeError('secret latitude=45.75')):
            received = w.weather_for(CITY, refresh=True, network=True)
        self.assertTrue(received['stale'])
        self.assertEqual(out.getvalue(), '')
        diagnostic = json.loads(err.getvalue().splitlines()[0])
        self.assertEqual(diagnostic['event'], 'owee.error')
        self.assertEqual(diagnostic['error_type'], 'RuntimeError')
        self.assertNotIn('45.75', err.getvalue())
        self.assertNotIn('secret', err.getvalue())


if __name__ == '__main__':
    unittest.main()
