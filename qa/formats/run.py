#!/usr/bin/env python3
"""Native QtTest checks for formatting; all writable paths are disposable."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent


def main():
    for timezone in ('UTC', 'Asia/Kathmandu', 'America/New_York'):
        with tempfile.TemporaryDirectory(prefix='owee-formats-') as temporary:
            base = Path(temporary)
            (base / 'Commons').symlink_to('/usr/share/omarchy/shell/Commons', target_is_directory=True)
            (base / 'services').symlink_to('/usr/share/omarchy/shell/services', target_is_directory=True)
            (base / 'plugin').mkdir()
            shutil.copy2(ROOT / 'WeatherFormats.qml', base / 'plugin/WeatherFormats.qml')
            shutil.copy2(HERE / 'tst_formats.qml', base / 'shell.qml')
            env = os.environ.copy()
            env.update(TZ=timezone, QT_QPA_PLATFORM='offscreen', QT_QUICK_BACKEND='software',
                       XDG_CONFIG_HOME=str(base / 'config'), XDG_STATE_HOME=str(base / 'state'),
                       XDG_CACHE_HOME=str(base / 'cache'), XDG_DATA_HOME=str(base / 'data'))
            try:
                result = subprocess.run(['quickshell', '--no-color', '-p', str(base)], env=env,
                                        text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                        timeout=15)
            except subprocess.TimeoutExpired as error:
                print(error.stdout.decode(errors='replace') if isinstance(error.stdout, bytes) else error.stdout)
                return 1
            print(timezone + ':\n' + result.stdout)
            if result.returncode or 'QA_FORMATS_PASS' not in result.stdout or 'FAIL!' in result.stdout:
                return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
