#!/usr/bin/env python3
"""Check real OWEE payloads against the installed shell's notification policy.

Notification delivery is mocked. Only trusted installed Omarchy JS is imported;
all generated files and writable XDG paths live in a disposable test directory.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
SHELL = Path('/usr/share/omarchy/shell/plugins/notifications')
sys.path.insert(0, str(ROOT))
import notifications


def payloads():
    now = datetime(2026, 11, 13, 9, 15, tzinfo=timezone.utc)
    stamp = now.timestamp()
    settings = {**notifications.DEFAULTS, 'enabled': True, 'quiet_enabled': False,
                'daily': True, 'daily_time': now.astimezone().strftime('%H:%M')}
    names = ['Your verification code is 482913', 'OTP A9F3K2', 'verification G-482913',
             'Code 482 913', '<img src="https://example.invalid/probe">',
             'Paris\nPIN 482913', '東京都', 'São Paulo', 'مدينة 482913 verification']
    cases = []
    with patch.object(notifications.subprocess, 'run') as delivery:
        for name in names:
            result = {'city': {'name': name, 'latitude': 45.75, 'longitude': 4.85},
                      'updated': stamp, 'stale': False, 'unit': 'C',
                      'data': {'timezone': 'UTC',
                               'current': {'time_utc': stamp, 'temperature_2m': 12, 'wind_speed_10m': 55},
                               'hourly': {'time': ['2026-11-13T10:15'], 'time_utc': [stamp + 3600],
                                          'precipitation_probability': [80]},
                               'daily': {'time': ['2026-11-13'], 'uv_index_max': [7],
                                         'temperature_2m_min': [8], 'temperature_2m_max': [16]}}}
            candidates = notifications.evaluate(result, settings, now)
            if {item['kind'] for item in candidates} != {'rain', 'wind', 'uv', 'daily'}:
                raise ValueError('Fixture did not exercise every automatic notification')
            for candidate in candidates:
                notifications._send(candidate['title'], candidate['body'])
            notifications.send_test(result['city'])
        for call in delivery.call_args_list:
            command = call.args[0]
            if command[0] != 'notify-send' or '--app-name=OWEE' not in command:
                raise ValueError('Unexpected notification delivery identity')
            cases.append({'summary': command[-2], 'body': command[-1], 'app': 'OWEE', 'urgency': 1})
    if len(cases) != len(names) * 5:
        raise ValueError('Missing automatic or test notification payload')
    return cases


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'reports/notification-policy')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    sources = {name: hashlib.sha256((SHELL / name).read_bytes()).hexdigest()
               for name in ('Detect.js', 'Delivery.js', 'Security.js')}
    cases = payloads()
    with tempfile.TemporaryDirectory(prefix='owee-notification-policy-') as temporary:
        base = Path(temporary)
        (base / 'native').symlink_to(SHELL, target_is_directory=True)
        qml = (HERE / 'tst_policy.qml').read_text().replace('@@CASES@@', json.dumps(cases))
        (base / 'shell.qml').write_text(qml)
        env = os.environ.copy()
        env.update(QT_QPA_PLATFORM='offscreen', QT_QUICK_BACKEND='software',
                   XDG_CONFIG_HOME=str(base / 'config'), XDG_STATE_HOME=str(base / 'state'),
                   XDG_CACHE_HOME=str(base / 'cache'), XDG_DATA_HOME=str(base / 'data'))
        result = subprocess.run(['quickshell', '--no-color', '-p', str(base)], env=env,
                                text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=15)
    (args.output / 'test.log').write_text(result.stdout)
    print(result.stdout, end='')
    passed = result.returncode == 0 and 'QA_NOTIFICATION_POLICY_PASS' in result.stdout and 'QA_FAIL' not in result.stdout
    report = {'status': 'passed' if passed else 'failed', 'payloads': len(cases),
              'shell_sources_sha256': sources, 'real_notifications_sent': 0}
    (args.output / 'summary.json').write_text(json.dumps(report, indent=2) + '\n')
    return 0 if passed else 1


if __name__ == '__main__':
    raise SystemExit(main())
