import importlib.util
import copy
import json
import sys
import tempfile
import time
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch
from zoneinfo import ZoneInfo

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
spec = importlib.util.spec_from_file_location('weather', Path(__file__).resolve().parents[1] / 'weather.py')
w = importlib.util.module_from_spec(spec)
spec.loader.exec_module(w)

DATA = {'current': {'temperature_2m': 12, 'time': '2026-11-12T10:15'}, 'hourly': {'time': ['2026-11-12T10:00']}, 'daily': {'time': ['2026-11-12']}, 'timezone': 'Europe/Paris'}

class WeatherTests(unittest.TestCase):
    def setUp(self):
        # The API fixture is historical; control its observation and download clocks together.
        observed = datetime.fromisoformat(DATA['current']['time']).replace(tzinfo=ZoneInfo(DATA['timezone']))
        self.clock = patch.object(w.time, 'time', return_value=observed.timestamp())
        self.clock.start()
        self.addCleanup(self.clock.stop)
        self.old_min_refresh = w.MIN_REFRESH_SECONDS
        w.MIN_REFRESH_SECONDS = 0  # Existing refresh scenarios intentionally bypass the new manual cooldown.
        self.temp = tempfile.TemporaryDirectory()
        self.old_state = w.STATE
        w.STATE = Path(self.temp.name)
    def tearDown(self):
        w.MIN_REFRESH_SECONDS = self.old_min_refresh
        w.STATE = self.old_state
        self.temp.cleanup()
    @patch.object(w, 'request', return_value=DATA)
    def test_forecast_and_cache_offline(self, request):
        live = w.main(['load'])
        self.assertEqual(live['city']['name'], 'Lyon')
        self.assertFalse(live['stale'])
        request.side_effect = OSError('offline')
        offline = w.main(['load'])
        self.assertTrue(offline['stale'])
        self.assertEqual(offline['data']['current']['temperature_2m'], 12)
    @patch.object(w, 'request', return_value=DATA)
    def test_selection_and_unit_are_persisted(self, request):
        city = {'name':'Paris', 'latitude':48.85, 'longitude':2.35}
        self.assertEqual(w.main(['select', json.dumps(city)])['city']['name'], 'Paris')
        self.assertEqual(w.main(['unit', 'F'])['unit'], 'F')
        self.assertEqual(w.main(['load'])['city']['name'], 'Paris')
        self.assertEqual(w.main(['load'])['unit'], 'F')
    @patch.object(w, 'request', return_value=DATA)
    def test_auto_refresh_preference_persists(self, request):
        self.assertFalse(w.main(['auto', 'off'])['auto_refresh'])
        self.assertFalse(w.main(['load'])['auto_refresh'])
        self.assertTrue(w.main(['auto', 'on'])['auto_refresh'])

    @patch.object(w, 'request', side_effect=OSError('offline'))
    def test_failed_selection_does_not_change_saved_city(self, request):
        w.save_json(w.STATE / 'settings.json', {'city': w.DEFAULT})
        with self.assertRaises(OSError):
            w.main(['select', json.dumps({'name':'Paris', 'latitude':48.85, 'longitude':2.35})])
        self.assertEqual(w.read_json(w.STATE / 'settings.json', {})['city']['name'], 'Lyon')
    @patch.object(w, 'request', return_value=DATA)
    def test_favorites_order_removal_and_offline_cache_per_city(self, request):
        paris = {'name':'Paris', 'latitude':48.85, 'longitude':2.35}
        w.main(['load'])
        w.main(['select', json.dumps(paris)])
        cities = w.main(['move-city', json.dumps({'key':w.city_key(paris), 'direction':'up'})])['cities']
        self.assertEqual([c['name'] for c in cities], ['Paris', 'Lyon'])
        request.side_effect = OSError('offline')
        lyon = next(c for c in cities if c['name'] == 'Lyon')
        selected = w.main(['select', json.dumps(lyon)])
        self.assertTrue(selected['stale'])
        self.assertEqual(selected['city']['name'], 'Lyon')
        result = w.main(['remove', w.city_key(lyon)])
        self.assertEqual(result['city']['name'], 'Paris')
        self.assertEqual(result['data']['current']['temperature_2m'], 12)
        self.assertEqual([c['name'] for c in result['cities']], ['Paris'])

    @patch.object(w, 'request', return_value=DATA)
    def test_card_preferences_persist_without_unnecessary_network(self, request):
        w.main(['load'])
        request.reset_mock()
        r = w.main(['cards', json.dumps({'id':'air','op':'toggle'})])
        self.assertIn('air', r['hidden_cards'])
        w.main(['cards', json.dumps({'id':'air','op':'up'})])
        self.assertLess(w.main(['cards', json.dumps({'id':'air','op':'up'})])['cards'].index('air'), w.CARD_IDS.index('air'))
        request.assert_not_called()
        saved = w.read_json(w.STATE / 'settings.json', {})
        self.assertIn('air', saved['hidden_cards'])

    def test_air_failure_does_not_lose_main_forecast(self):
        def api(url, params):
            if url == w.AIR: raise OSError('air unavailable')
            return DATA
        with patch.object(w, 'request', side_effect=api):
            result = w.main(['load'])
        self.assertEqual(result['data']['air'], {})
        self.assertEqual(result['data']['current']['temperature_2m'], 12)

    def test_reject_bad_coordinates(self):
        for val in (float('nan'), 91, float('inf')):
            with self.assertRaises(ValueError):
                w.location({'name': 'X', 'latitude': val, 'longitude': 0})
    def test_mismatched_cache_is_not_shown(self):
        w.save_json(w.STATE / 'forecast.json', {'city': {'name':'Paris', 'latitude':48.85, 'longitude':2.35}, 'data': DATA})
        with patch.object(w, 'request', side_effect=OSError('offline')):
            result = w.main(['load'])
        self.assertEqual(result['city']['name'], 'Lyon')
        self.assertNotIn('data', result)
    def test_qml_displays_network_text_as_plain_text(self):
        qml = (Path(__file__).resolve().parents[1] / 'PText.qml').read_text()
        self.assertIn('textFormat: Text.PlainText', qml)
        self.assertEqual(w.location({'name':'<img src="https://example.invalid/x">', 'latitude':1, 'longitude':2})['name'], '<img src="https://example.invalid/x">')

    @patch.object(w, 'request', return_value=DATA)
    def test_notification_settings_preserve_favorites_and_do_not_fetch(self, request):
        w.main(['load'])
        w.main(['cards', json.dumps({'id':'air','op':'toggle'})])
        request.reset_mock()
        result = w.main(['notifications', json.dumps({'enabled':True, 'rain_probability':70})])
        request.assert_not_called()
        self.assertEqual(result['notifications']['rain_probability'], 70)
        saved = w.read_json(w.STATE / 'settings.json', {})
        self.assertTrue(saved['notifications']['enabled'])
        self.assertIn('air', saved['hidden_cards'])
        self.assertEqual(saved['cities'][0]['name'], 'Lyon')

    @patch.object(w.notifications, 'dispatch', return_value={'sent':0})
    @patch.object(w, 'request', return_value=DATA)
    def test_notifications_only_on_load_and_cache_tick(self, request, dispatch):
        w.main(['load'])
        self.assertEqual(dispatch.call_count, 1)
        w.main(['unit','F'])
        w.main(['notifications',json.dumps({'enabled':True})])
        self.assertEqual(dispatch.call_count, 1)
        request.reset_mock()
        w.main(['notify'])
        request.assert_not_called()
        self.assertEqual(dispatch.call_count, 2)
        w.main(['auto','off'])
        w.main(['notify'])
        w.main(['load'])
        self.assertEqual(dispatch.call_count, 2)

    @patch.object(w.notifications, 'send_test', return_value={'sent':1})
    @patch.object(w, 'request')
    def test_manual_notification_test_does_not_use_network_or_enable_notifications(self, request, send):
        self.assertEqual(w.main(['notify-test'])['notification_status']['sent'], 1)
        request.assert_not_called()
        send.assert_called_once()
        self.assertFalse((w.STATE / 'settings.json').exists())

    def test_malformed_cache_falls_back_without_crashing(self):
        w.save_json(w.cache_for(w.DEFAULT), [])
        with patch.object(w, 'request', side_effect=OSError('offline')):
            result = w.main(['load'])
        self.assertIn('error', result)
        self.assertIn('notifications', result)

    @patch.object(w.notifications, 'dispatch', return_value={'sent':0})
    @patch.object(w, 'request', return_value=DATA)
    def test_offline_refresh_marks_cache_stale_for_notification_timer(self, request, dispatch):
        w.main(['load'])
        request.side_effect = OSError('offline')
        self.assertTrue(w.main(['load'])['stale'])
        self.assertTrue(w.read_json(w.cache_for(w.DEFAULT), {})['stale'])
        dispatch.reset_mock()
        w.main(['notify'])
        self.assertTrue(dispatch.call_args.args[0]['stale'])
        request.side_effect = None
        self.assertFalse(w.main(['load'])['stale'])
        self.assertFalse(w.read_json(w.cache_for(w.DEFAULT), {})['stale'])

    @patch.object(w, 'request', return_value=DATA)
    def test_migration_keeps_old_city_as_primary_when_browsing_another(self, request):
        paris = {'name':'Paris', 'latitude':48.85, 'longitude':2.35}
        w.save_json(w.STATE / 'settings.json', {'city':paris, 'unit':'F', 'hidden_cards':['air']})
        migrated = w.main(['load'])
        self.assertEqual(migrated['primary_city']['name'], 'Paris')
        saved = w.read_json(w.STATE / 'settings.json', {})
        self.assertEqual(saved['primary_city']['name'], 'Paris')
        self.assertEqual(saved['unit'], 'F')
        self.assertEqual(saved['hidden_cards'], ['air'])
        selected = w.main(['select', json.dumps(w.DEFAULT)])
        self.assertEqual(selected['city']['name'], 'Lyon')
        self.assertEqual(selected['primary']['city']['name'], 'Paris')
        self.assertEqual(w.main(['load'])['primary_city']['name'], 'Paris')

    @patch.object(w, 'request', return_value=DATA)
    def test_first_selection_before_migration_load_keeps_previous_primary(self, request):
        paris = {'name':'Paris', 'latitude':48.85, 'longitude':2.35}
        w.save_json(w.STATE / 'settings.json', {'city':w.DEFAULT})
        selected = w.main(['select', json.dumps(paris)])
        self.assertEqual(selected['city']['name'], 'Paris')
        self.assertEqual(selected['primary_city']['name'], 'Lyon')
        self.assertEqual(w.read_json(w.STATE / 'settings.json', {})['primary_city']['name'], 'Lyon')

    def city_forecast(self, city, temperature=12):
        data = copy.deepcopy(DATA)
        data['current']['temperature_2m'] = temperature
        return {'city':city, 'data':data, 'updated':int(time.time()), 'stale':False}

    @patch.object(w.notifications, 'dispatch', return_value={'sent':0})
    def test_distinct_primary_has_independent_weather_and_refreshes_once(self, dispatch):
        paris = w.location({'name':'Paris', 'latitude':48.85, 'longitude':2.35})
        w.save_json(w.STATE / 'settings.json', {'city':paris, 'primary_city':w.DEFAULT,
                                              'cities':[w.DEFAULT, paris]})
        with patch.object(w, 'forecast', side_effect=lambda c:self.city_forecast(c, 8 if c['name']=='Lyon' else 19)) as fetch:
            result = w.main(['load'])
        self.assertEqual([call.args[0]['name'] for call in fetch.call_args_list], ['Lyon','Paris'])
        self.assertEqual(result['data']['current']['temperature_2m'], 19)
        self.assertEqual(result['primary']['data']['current']['temperature_2m'], 8)
        self.assertNotIn('primary', result['primary'])
        self.assertEqual(dispatch.call_args.args[0]['city']['name'], 'Lyon')
        self.assertEqual(dispatch.call_args.args[0]['data']['current']['temperature_2m'], 8)

    @patch.object(w, 'forecast')
    def test_same_primary_and_display_are_only_refreshed_once(self, fetch):
        fetch.side_effect = lambda c:self.city_forecast(c)
        result = w.main(['load'])
        fetch.assert_called_once()
        self.assertEqual(result['primary_city'], result['city'])
        self.assertIsNot(result, result['primary'])

    @patch.object(w, 'request', return_value=DATA)
    def test_marking_primary_keeps_the_consulted_city_and_uses_cache(self, request):
        paris = {'name':'Paris', 'latitude':48.85, 'longitude':2.35}
        w.main(['load'])
        w.main(['select', json.dumps(paris)])
        w.main(['select', json.dumps(w.DEFAULT)])
        request.reset_mock()
        selected = w.main(['primary',w.city_key(paris)])
        request.assert_not_called()
        self.assertEqual(selected['city']['name'], 'Lyon')
        self.assertEqual(selected['primary']['city']['name'], 'Paris')
        self.assertEqual(w.read_json(w.STATE / 'settings.json', {})['primary_city']['name'], 'Paris')

    @patch.object(w.notifications, 'dispatch', return_value={'sent':0})
    @patch.object(w.notifications, 'send_test', return_value={'sent':1})
    @patch.object(w, 'request', return_value=DATA)
    def test_notification_ticks_and_tests_follow_primary_instead_of_browsed_city(self, request, send, dispatch):
        paris = {'name':'Paris', 'latitude':48.85, 'longitude':2.35}
        w.main(['load'])
        w.main(['select',json.dumps(paris)])
        w.main(['unit','F'])
        request.reset_mock()
        w.main(['notify'])
        w.main(['notify-test'])
        request.assert_not_called()
        self.assertEqual(dispatch.call_args.args[0]['city']['name'], 'Lyon')
        self.assertEqual(dispatch.call_args.args[0]['unit'], 'F')
        self.assertEqual(send.call_args.args[0]['name'], 'Lyon')

    @patch.object(w.notifications, 'dispatch', return_value={'sent':0})
    def test_view_offline_does_not_mark_live_primary_offline(self, dispatch):
        paris = w.location({'name':'Paris', 'latitude':48.85, 'longitude':2.35})
        w.save_json(w.STATE / 'settings.json', {'city':paris, 'primary_city':w.DEFAULT,
                                              'cities':[w.DEFAULT,paris]})
        w.save_json(w.cache_for(paris), self.city_forecast(paris,19))
        def api(city):
            if city['name'] == 'Paris': raise OSError('offline Paris')
            return self.city_forecast(city,8)
        with patch.object(w,'forecast',side_effect=api):
            result = w.main(['load'])
        self.assertTrue(result['stale'])
        self.assertFalse(result['primary']['stale'])
        self.assertFalse(dispatch.call_args.args[0]['stale'])
        self.assertEqual(dispatch.call_args.args[0]['city']['name'],'Lyon')

    @patch.object(w.notifications, 'dispatch', return_value={'sent':0})
    def test_primary_offline_stays_separate_from_live_browsed_city(self, dispatch):
        paris = w.location({'name':'Paris', 'latitude':48.85, 'longitude':2.35})
        w.save_json(w.STATE / 'settings.json', {'city':paris, 'primary_city':w.DEFAULT,
                                              'cities':[w.DEFAULT,paris]})
        w.save_json(w.cache_for(w.DEFAULT), self.city_forecast(w.DEFAULT,8))
        def api(city):
            if city['name'] == 'Lyon': raise OSError('offline Lyon')
            return self.city_forecast(city,19)
        with patch.object(w,'forecast',side_effect=api):
            result = w.main(['load'])
        self.assertFalse(result['stale'])
        self.assertTrue(result['primary']['stale'])
        self.assertTrue(dispatch.call_args.args[0]['stale'])

    @patch.object(w, 'request', return_value=DATA)
    def test_removing_primary_promotes_the_viewed_city(self, request):
        paris = {'name':'Paris', 'latitude':48.85, 'longitude':2.35}
        w.main(['load'])
        w.main(['select',json.dumps(paris)])
        result = w.main(['remove',w.city_key(w.DEFAULT)])
        self.assertEqual(result['city']['name'],'Paris')
        self.assertEqual(result['primary_city']['name'],'Paris')
        self.assertEqual(w.read_json(w.STATE/'settings.json',{})['primary_city']['name'],'Paris')
        self.assertEqual(len(w.main(['remove',w.city_key(paris)])['cities']),1)

    @patch.object(w, 'request', return_value=DATA)
    def test_removing_viewed_city_returns_to_primary(self, request):
        paris = {'name':'Paris', 'latitude':48.85, 'longitude':2.35}
        w.main(['load'])
        w.main(['select',json.dumps(paris)])
        result = w.main(['remove',w.city_key(paris)])
        self.assertEqual(result['city']['name'],'Lyon')
        self.assertEqual(result['primary_city']['name'],'Lyon')

    def test_invalid_primary_or_failed_uncached_primary_change_preserves_preferences(self):
        paris = w.location({'name':'Paris','latitude':48.85,'longitude':2.35})
        initial = {'city':w.DEFAULT,'primary_city':w.DEFAULT,'cities':[w.DEFAULT,paris]}
        w.save_json(w.STATE/'settings.json',initial)
        original = (w.STATE/'settings.json').read_bytes()
        with self.assertRaises(ValueError):
            w.main(['primary','1.00000,2.00000'])
        with patch.object(w,'forecast',side_effect=OSError('offline')):
            with self.assertRaises(OSError):
                w.main(['primary',w.city_key(paris)])
        self.assertEqual((w.STATE/'settings.json').read_bytes(),original)

    def test_mismatched_or_nameless_cache_cannot_make_selection_succeed_offline(self):
        paris = w.location({'name':'Paris','latitude':48.85,'longitude':2.35})
        w.save_json(w.STATE/'settings.json',{'city':w.DEFAULT,'primary_city':w.DEFAULT})
        for cached_city in (w.DEFAULT,{**paris,'name':''}):
            w.save_json(w.cache_for(paris),self.city_forecast(cached_city))
            with patch.object(w,'forecast',side_effect=OSError('offline')):
                with self.assertRaises(OSError):
                    w.main(['select',json.dumps(paris)])
            self.assertEqual(w.read_json(w.STATE/'settings.json',{})['city']['name'],'Lyon')

    @patch.object(w,'request')
    def test_preferences_without_any_weather_cache_do_not_contact_network(self, request):
        for action in (['unit','F'],['auto','off'],['notifications',json.dumps({'enabled':True})],
                       ['cards',json.dumps({'id':'air','op':'toggle'})]):
            result = w.main(action)
            self.assertIn('primary', result)
        request.assert_not_called()

    @patch.object(w,'request',return_value=DATA)
    def test_reorder_is_persisted_as_one_complete_order_without_changing_hidden_cards(self, request):
        w.main(['load'])
        w.main(['cards',json.dumps({'id':'air','op':'toggle'})])
        request.reset_mock()
        order = list(reversed(w.CARD_IDS))
        result = w.main(['cards',json.dumps({'op':'reorder','order':order})])
        self.assertEqual(result['cards'],order)
        self.assertEqual(result['hidden_cards'],['air'])
        self.assertEqual(w.read_json(w.STATE/'settings.json',{})['cards'],order)
        request.assert_not_called()

    def test_invalid_reorder_is_rejected_without_mutating_saved_preferences(self):
        w.save_json(w.STATE/'settings.json',{'city':w.DEFAULT,'cards':w.CARD_IDS,'hidden_cards':['air']})
        original = (w.STATE/'settings.json').read_bytes()
        for order in (None,[],w.CARD_IDS[:-1],w.CARD_IDS[:-1]+['wind'],
                      w.CARD_IDS[:-1]+['unknown'],w.CARD_IDS[:-1]+[{}],w.CARD_IDS+[w.CARD_IDS[0]]):
            with self.subTest(order=order):
                with self.assertRaises(ValueError):
                    w.main(['cards',json.dumps({'op':'reorder','order':order})])
                self.assertEqual((w.STATE/'settings.json').read_bytes(),original)

    @patch.object(w,'request',return_value=DATA)
    def test_primary_outside_favorites_is_repaired_without_adding_a_favorite(self, request):
        paris = w.location({'name':'Paris','latitude':48.85,'longitude':2.35})
        w.save_json(w.STATE/'settings.json',{'city':w.DEFAULT,'primary_city':paris,'cities':[w.DEFAULT]})
        result = w.main(['load'])
        self.assertEqual(result['primary_city']['name'],'Lyon')
        self.assertEqual([c['name'] for c in result['cities']],['Lyon'])

if __name__ == '__main__':
    unittest.main()
