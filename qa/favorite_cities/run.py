#!/usr/bin/env python3
"""Exercise favorite navigation with real native controls and isolated workers.

Only the disposable plugin copy changes. Backend fixtures never use network,
notifications, the installed plugin, or the user's preferences.
"""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / 'qa'))
from ui_layout.run import prepare


def signal_group(process, signum):
    try:
        os.killpg(process.pid, signum)
    except ProcessLookupError:
        pass


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plugin', type=Path, default=ROOT)
    parser.add_argument('--output', type=Path, default=ROOT / 'reports/favorite-cities')
    parser.add_argument('--scale', type=float, default=1)
    args = parser.parse_args()
    if not 0.5 <= args.scale <= 3:
        parser.error('--scale must be between 0.5 and 3')
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='owee-favorite-cities-') as temporary:
        base = Path(temporary)
        plugin = prepare(base, args.plugin, output)
        fixture_path = plugin / 'fixture-state.json'
        fixture = json.loads(fixture_path.read_text())
        fixture['cities'] = fixture['cities'][:2] + [
            {'name': 'Fixture failure', 'latitude': 3, 'longitude': 4},
            {'name': '<img src="https://example.invalid/probe"> Ville', 'latitude': 1, 'longitude': 2},
        ] + [
            {'name': f'Favorite {index:02d} with a very long city name',
             'latitude': 10 + index / 10, 'longitude': 20 + index / 10}
            for index in range(4, 30)
        ]
        fixture_path.write_text(json.dumps(fixture, ensure_ascii=False))
        backend_path = plugin / 'weather.py'
        backend = backend_path.read_text()
        failure = '''if name=='weather':
    if action=='select':
        time.sleep(0.3)
        if json.loads(arg)['name']=='Fixture failure':
            print(json.dumps({'error':'Fixture favorite selection failure'}));sys.exit()
'''
        backend_path.write_text(backend.replace("if name=='weather':\n", failure, 1))
        (base / 'shell.qml').write_text((HERE / 'tst_favorites.qml').read_text())
        env = os.environ.copy()
        env.update(QT_QPA_PLATFORM='offscreen', QT_QUICK_BACKEND='software', QT_SCALE_FACTOR=str(args.scale),
                   XDG_STATE_HOME=str(base / 'state'), XDG_CACHE_HOME=str(base / 'cache'),
                   XDG_CONFIG_HOME=str(base / 'config'), XDG_DATA_HOME=str(base / 'data'))
        # Log directly to disk: a crash helper inheriting stdout must neither
        # discard partial diagnostics nor keep communicate() waiting for EOF.
        timed_out = False
        with (output / 'test.log').open('w') as log:
            process = subprocess.Popen(['quickshell', '--no-color', '-p', str(base)],
                                       env=env, text=True, stdout=log,
                                       stderr=subprocess.STDOUT, start_new_session=True)
            try:
                returncode = process.wait(timeout=25)
            except subprocess.TimeoutExpired:
                timed_out = True
                signal_group(process, signal.SIGTERM)
                try:
                    returncode = process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    signal_group(process, signal.SIGKILL)
                    returncode = process.wait(timeout=2)
                log.write('\nQA_FAIL: favorite suite exceeded 25-second process deadline\n')
            finally:
                # Quickshell crash helpers may outlive the launched process.
                # This new session contains only this disposable test run.
                signal_group(process, signal.SIGKILL)
        stdout = (output / 'test.log').read_text()
        print(stdout, end='')
        trace_path = plugin / 'backend-trace.jsonl'
        trace = [json.loads(row) for row in trace_path.read_text().splitlines()] if trace_path.exists() else []
        (output / 'backend-trace.json').write_text(json.dumps(trace, indent=2, ensure_ascii=False) + '\n')
        if (timed_out or returncode or 'QA_FAVORITE_CITIES_PASS' not in stdout
                or 'QA_FAIL' in stdout or 'ERROR' in stdout):
            raise SystemExit(1)
        actions = [row['action'] for row in trace if row['name'] == 'weather']
        selections = [json.loads(row['arg'])['name'] for row in trace
                      if row['name'] == 'weather' and row['action'] == 'select']
        expected = ['Lyon', 'Paris', 'Lyon', 'Paris', 'Fixture failure']
        if selections != expected:
            raise SystemExit('QA_FAIL: duplicate or missing favorite selection: ' + repr(selections))
        if 'primary' in actions or any(action not in ('load', 'air', 'select') for action in actions):
            raise SystemExit('QA_FAIL: favorites changed primary city or used an unexpected worker: ' + repr(actions))
        state = json.loads(fixture_path.read_text())
        if state['primary_city'] != fixture['primary_city'] or state['primary'] != fixture['primary']:
            raise SystemExit('QA_FAIL: favorite navigation mutated primary weather')
        print('QA_FAVORITE_CITIES_TRAFFIC_PASS: five explicit selections; same city is free; primary weather unchanged')


if __name__ == '__main__':
    main()
