#!/usr/bin/env python3
"""One-shot local release continuation. Never creates or pushes a remote."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
VERSION = json.loads((ROOT/'manifest.json').read_text())['version']
REPORT = ROOT / ('reports/endurance-'+VERSION+'/summary.json')
STATE = ROOT / 'reports/local-finalization.json'
UNIT = 'owee-qualification-'+VERSION+'.service'
EXPECTED_COMMIT = None
EXPECTED_DIGEST = None
INSTALL = Path.home() / '.config/omarchy/plugins/owee.weather'


def run(command, timeout=30):
    return subprocess.check_output(command, cwd=ROOT, text=True,
                                   stderr=subprocess.STDOUT, timeout=timeout).strip()


def save(status, **details):
    data = {'status': status, 'updated_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
            'remote_published': False, **details}
    tmp = STATE.with_suffix('.tmp')
    tmp.write_text(json.dumps(data, indent=2) + '\n')
    os.replace(tmp, STATE)
    print(json.dumps(data), flush=True)


def prerequisites():
    if run(['git', 'rev-parse', 'HEAD']) != EXPECTED_COMMIT:
        raise RuntimeError('Candidate HEAD changed; review before finalizing')
    if run(['git', 'status', '--porcelain']):
        raise RuntimeError('Candidate has local changes')
    if run(['git', '-C', str(INSTALL), 'status', '--porcelain']):
        raise RuntimeError('Installed plugin has local changes')
    if run(['git', '-C', str(INSTALL), 'rev-parse', 'HEAD']) != EXPECTED_COMMIT:
        raise RuntimeError('Installed plugin changed; preserve it for review')
    if run(['git', '-C', str(INSTALL), 'remote', 'get-url', 'origin']) != str(ROOT):
        raise RuntimeError('Installed origin changed; refusing automatic update')
    report = json.loads(REPORT.read_text())
    if report.get('source_sha256') != EXPECTED_DIGEST:
        raise RuntimeError('Endurance report belongs to different source')
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check-only', action='store_true')
    parser.add_argument('--candidate-commit', required=True)
    parser.add_argument('--source-sha256', required=True)
    args = parser.parse_args()
    global EXPECTED_COMMIT, EXPECTED_DIGEST
    EXPECTED_COMMIT = args.candidate_commit
    EXPECTED_DIGEST = args.source_sha256
    report = prerequisites()
    if args.check_only:
        result = subprocess.run([sys.executable, '-B', 'tools/promote.py'], cwd=ROOT)
        return result.returncode
    while report.get('status') == 'running':
        active = run(['systemctl', '--user', 'show', UNIT, '-p', 'ActiveState', '--value'])
        if active not in ('active', 'activating'):
            # Read once more after the process has stopped to allow its final write.
            report = prerequisites()
            if report.get('status') == 'running':
                raise RuntimeError('Endurance stopped without a final report')
            break
        if time.time() - REPORT.stat().st_mtime > 300:
            raise RuntimeError('Endurance report has stopped progressing')
        save('waiting_for_endurance', elapsed_seconds=report.get('elapsed_seconds'),
             completed_cycles=report.get('completed_cycles'))
        time.sleep(60)
        report = prerequisites()
    if report.get('status') != 'passed' or report.get('qualified') is not True:
        raise RuntimeError('Endurance did not qualify: ' + json.dumps(report.get('failures', [])))
    save('promoting_locally')
    with (ROOT / 'reports/local-finalization.log').open('a') as log:
        subprocess.run([sys.executable, '-B', 'tools/promote.py', '--apply'], cwd=ROOT,
                       stdout=log, stderr=subprocess.STDOUT, timeout=1800, check=True)
        promotion = json.loads((ROOT/'reports/promotion.json').read_text())
        stable_commit = promotion['stable_commit']
        # Recheck the installed checkout before the native updater touches it.
        if run(['git', '-C', str(INSTALL), 'status', '--porcelain']):
            raise RuntimeError('Installed plugin changed during promotion')
        if run(['git', '-C', str(INSTALL), 'rev-parse', 'HEAD']) != EXPECTED_COMMIT:
            raise RuntimeError('Installed HEAD changed during promotion')
        if run(['git', '-C', str(INSTALL), 'remote', 'get-url', 'origin']) != str(ROOT):
            raise RuntimeError('Installed origin changed during promotion')
        save('updating_installed_plugin', stable_commit=stable_commit)
        run(['git', '-C', str(INSTALL), 'fetch', 'origin', 'refs/heads/main'])
        if run(['git', '-C', str(INSTALL), 'rev-parse', 'FETCH_HEAD']) != stable_commit:
            raise RuntimeError('Fetched main differs from qualified release')
        run(['git', '-C', str(INSTALL), 'merge', '--ff-only', stable_commit])
        run(['omarchy', 'plugin', 'validate', str(INSTALL)])
        run(['omarchy-shell', 'shell', 'rescanPlugins'])
    installed_commit = run(['git', '-C', str(INSTALL), 'rev-parse', 'HEAD'])
    version = json.loads((INSTALL / 'manifest.json').read_text())['version']
    if installed_commit != stable_commit or version != VERSION.split('-rc.',1)[0]:
        raise RuntimeError('Installed revision does not match qualified stable source')
    save('stable_installed', version=version, stable_commit=stable_commit,
         endurance_report=str(REPORT), public_publication='pending GitHub authentication')
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    except Exception as error:
        save('failed', error=str(error))
        raise
