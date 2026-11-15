#!/usr/bin/env python3
"""Exercise native preference migration and synchronization in real Quickshell.

The native shell persistence seam is doubled in memory. All Python workers use
local fixtures, and the user's settings, network and notification service are
never touched. Temperature locale injection changes only the disposable copy.
"""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(0, str(ROOT / 'qa'))
from ui_layout.run import prepare


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--plugin', type=Path, default=ROOT)
    parser.add_argument('--output', type=Path, default=ROOT / 'reports/native-preferences')
    parser.add_argument('--scale', type=float, default=1)
    args = parser.parse_args()
    if not 0.5 <= args.scale <= 3:
        parser.error('--scale must be between 0.5 and 3')
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='owee-native-preferences-') as temporary:
        base = Path(temporary)
        plugin = prepare(base, args.plugin, output)
        fixture_path = plugin / 'fixture-state.json'
        fixture = json.loads(fixture_path.read_text())
        fixture.update(unit='F', auto_refresh=False)
        fixture_path.write_text(json.dumps(fixture))
        backend_path = plugin / 'weather.py'
        backend = backend_path.read_text()
        failure = '''if name=='weather':
    trace=[json.loads(row) for row in (base/'backend-trace.jsonl').read_text().splitlines()]
    units=sum(row['name']=='weather' and row['action']=='unit' for row in trace)
    if action=='unit' and arg=='C' and units>=5:
        print(json.dumps({'error':'Fixture preference storage failure'}));sys.exit()
'''
        backend_path.write_text(backend.replace("if name=='weather':\n", failure, 1))
        panel_path = plugin / 'Panel.qml'
        panel = panel_path.read_text()
        locale_seam = 'readonly property var systemLocale: Qt.locale(Commons.I18n.formatLocale)'
        if panel.count(locale_seam) != 1:
            raise SystemExit('QA_FAIL: native locale integration seam changed')
        panel_path.write_text(panel.replace(locale_seam, 'property var systemLocale: Qt.locale("en_US")', 1))
        (base / 'shell.qml').write_text((HERE / 'tst_preferences.qml').read_text())
        env = os.environ.copy()
        env.update(QT_QPA_PLATFORM='offscreen', QT_QUICK_BACKEND='software', QT_SCALE_FACTOR=str(args.scale),
                   XDG_STATE_HOME=str(base / 'state'), XDG_CACHE_HOME=str(base / 'cache'))
        result = subprocess.run(['timeout', '25s', 'quickshell', '--no-color', '-p', str(base)],
                                env=env, text=True, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, timeout=30)
        (output / 'test.log').write_text(result.stdout)
        print(result.stdout, end='')
        trace_path = plugin / 'backend-trace.jsonl'
        trace = [json.loads(row) for row in trace_path.read_text().splitlines()] if trace_path.exists() else []
        (output / 'backend-trace.json').write_text(json.dumps(trace, indent=2) + '\n')
        if (result.returncode or 'QA_NATIVE_PREFERENCES_PASS' not in result.stdout
                or 'QA_FAIL' in result.stdout or 'ERROR' in result.stdout):
            raise SystemExit(1)
        actions = [row['action'] for row in trace if row['name'] == 'weather']
        if actions.count('load') != 2 or any(action not in ('load', 'unit', 'auto', 'air') for action in actions):
            raise SystemExit('QA_FAIL: preferences caused a reload or unexpected worker: ' + repr(actions))
        commands = [(row['action'], row.get('arg')) for row in trace if row['name'] == 'weather']
        for command in (('unit', 'F'), ('unit', 'C'), ('auto', 'on'), ('auto', 'off')):
            if command not in commands:
                raise SystemExit('QA_FAIL: backend preference not synchronized: ' + repr(command))
        if actions.count('unit') != 5:
            raise SystemExit('QA_FAIL: preference failure retried automatically: ' + repr(actions))
        print('QA_NATIVE_PREFERENCES_TRAFFIC_PASS: preferences use only local unit/auto actions; exactly two initial loads')
        print('QA_NATIVE_PREFERENCES_FAILURE_PASS: failed local preference write has one attempt, no retry loop')


if __name__ == '__main__':
    main()
