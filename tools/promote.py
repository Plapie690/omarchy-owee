#!/usr/bin/env python3
"""Promote only source-matched, fully qualified candidates; never push remotely."""
import argparse
import json
import subprocess
import tempfile
import re
import os
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'qa'))
from endurance import source_digest,atomic_json,utc_now
sys.path.insert(0,str(ROOT))
from storage import lock


def evidence():
    digest=source_digest(ROOT)[0]
    required={'native':ROOT/'reports/qualification/summary.json',
              'international':ROOT/'reports/international.json',
              'maps':ROOT/'reports/live-maps.json',
              'endurance':ROOT/('reports/endurance-'+json.loads((ROOT/'manifest.json').read_text())['version']+'/summary.json')}
    failures=[];reports={}
    for name,path in required.items():
        try: report=json.loads(path.read_text())
        except (OSError,ValueError):failures.append(name+': missing report');continue
        reports[name]=report
        if report.get('status')!='passed':failures.append(name+': not passed')
        if report.get('source_sha256')!=digest:failures.append(name+': tested source differs')
    native=reports.get('native',{})
    if native.get('kind')!='native':failures.append('native GUI gates required')
    checks = {item.get('name') for item in native.get('checks',[]) if item.get('exit_code') == 0}
    if not {'lint','types','branches','qml','runtime','motion','formats','preferences','preferences150'}.issubset(checks):failures.append('quality gates required')
    endurance=reports.get('endurance',{})
    if not endurance.get('qualified') or endurance.get('elapsed_seconds',0)<43200 or endurance.get('completed_cycles',0)<1000:
        failures.append('twelve real hours and 1000 cycles required')
    if endurance.get('failures'):failures.append('endurance contains failures')
    return digest,failures,reports


def git(*args, cwd=None, input=None):
    return subprocess.check_output(['git', '-c', 'core.hooksPath=/dev/null', *args],
                                   cwd=cwd or ROOT, input=input, text=True).strip()


def qualify(worktree, output):
    subprocess.run([sys.executable, '-B', 'qa/qualify.py', '--native',
                    '--quality-python', os.environ.get('OWEE_QUALITY_PYTHON',sys.executable),
                    '--report-dir', str(output)], cwd=worktree, check=True, timeout=1800)


def promote(digest):
    """Keep the candidate checkout untouched; commit/tag stable refs atomically."""
    (ROOT/'reports').mkdir(parents=True, exist_ok=True)
    with lock(ROOT/'.release.lock'):
        if git('status', '--porcelain'):
            raise ValueError('Candidate checkout must be clean')
        if source_digest(ROOT)[0] != digest:
            raise ValueError('Tested source changed before promotion')
        if 'branch refs/heads/main' in git('worktree','list','--porcelain').splitlines():
            raise ValueError('Main is checked out; preserve its working tree')
        old = json.loads((ROOT/'manifest.json').read_text())['version']
        match = re.fullmatch(r'(\d+\.\d+\.\d+)-rc\.\d+', old)
        if not match:
            raise ValueError('A release candidate version is required')
        new = match.group(1)
        tag = 'refs/tags/v'+new
        if subprocess.run(['git','show-ref','--verify','--quiet',tag],cwd=ROOT).returncode == 0:
            raise ValueError('Stable tag already exists')
        head = git('rev-parse','HEAD')
        main = subprocess.run(['git','rev-parse','--verify','refs/heads/main'],cwd=ROOT,
                              capture_output=True,text=True)
        old_main = main.stdout.strip() if main.returncode == 0 else '0'*len(head)
        if main.returncode == 0:
            git('merge-base','--is-ancestor',old_main,head)
        output = ROOT/'reports/stable-qualification'
        with tempfile.TemporaryDirectory(prefix='owee-promote-') as temporary:
            worktree = Path(temporary)/'source'
            git('worktree','add','--detach',str(worktree),head)
            try:
                for name in ('manifest.json','Panel.qml','BarWidget.qml'):
                    path = worktree/name
                    text = path.read_text()
                    if text.count(old) != 1:
                        raise ValueError('Version marker mismatch: '+name)
                    path.write_text(text.replace(old,new))
                qualify(worktree,output)
                stable_digest = source_digest(worktree)[0]
                git('add','manifest.json','Panel.qml','BarWidget.qml',cwd=worktree)
                git('commit','-m','release: qualify OWEE '+new,cwd=worktree)
                stable_commit = git('rev-parse','HEAD',cwd=worktree)
                if git('rev-parse','HEAD') != head or git('status','--porcelain'):
                    raise ValueError('Candidate changed during promotion')
                if source_digest(ROOT)[0] != digest:
                    raise ValueError('Tested source changed during promotion')
                if 'branch refs/heads/main' in git('worktree','list','--porcelain').splitlines():
                    raise ValueError('Main was checked out during promotion')
                # Compare-and-swap main and create tag in the same ref transaction.
                git('update-ref','--stdin',input=(
                    'start\nupdate refs/heads/main '+stable_commit+' '+old_main+'\n'
                    'create '+tag+' '+stable_commit+'\nprepare\ncommit\n'))
            finally:
                git('worktree','remove','--force',str(worktree))
        report = {'status':'passed','candidate_source_sha256':digest,
                  'stable_source_sha256':stable_digest,'candidate_commit':head,
                  'stable_commit':stable_commit,'stable_branch':'main','tag':'v'+new,
                  'finished_at':utc_now(),'remote_published':False}
        atomic_json(ROOT/'reports/promotion.json',report)
        return report


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply',action='store_true')
    args=parser.parse_args()
    digest,failures,reports=evidence()
    if failures:
        print(json.dumps({'ready':False,'reasons':failures},indent=2));return 1
    if not args.apply:
        print(json.dumps({'ready':True,'candidate_source_sha256':digest,'remote_published':False}));return 0
    try:
        print(json.dumps(promote(digest)));return 0
    except Exception as error:
        atomic_json(ROOT/'reports/promotion.json',{'status':'failed','error':str(error),
                    'finished_at':utc_now(),'remote_published':False})
        raise


if __name__=='__main__':sys.exit(main())
