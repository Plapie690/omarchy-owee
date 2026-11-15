#!/usr/bin/env python3
"""Promote only source-matched, fully qualified candidates; never push remotely."""
import argparse
import json
import subprocess
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'qa'))
from endurance import source_digest,atomic_json,utc_now


def evidence():
    digest=source_digest(ROOT)[0]
    required={'native':ROOT/'reports/qualification/summary.json',
              'international':ROOT/'reports/international.json',
              'maps':ROOT/'reports/live-maps.json',
              'endurance':ROOT/'reports/endurance-1.3.0-rc.1/summary.json'}
    failures=[];reports={}
    for name,path in required.items():
        try: report=json.loads(path.read_text())
        except (OSError,ValueError):failures.append(name+': missing report');continue
        reports[name]=report
        if report.get('status')!='passed':failures.append(name+': not passed')
        if report.get('source_sha256')!=digest:failures.append(name+': tested source differs')
    native=reports.get('native',{})
    if native.get('kind')!='native':failures.append('native GUI gates required')
    endurance=reports.get('endurance',{})
    if not endurance.get('qualified') or endurance.get('elapsed_seconds',0)<43200 or endurance.get('completed_cycles',0)<1000:
        failures.append('twelve real hours and 1000 cycles required')
    if endurance.get('failures'):failures.append('endurance contains failures')
    return digest,failures,reports


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--apply',action='store_true');args=parser.parse_args()
    digest,failures,reports=evidence()
    if failures:
        print(json.dumps({'ready':False,'reasons':failures},indent=2));return 1
    print(json.dumps({'ready':True,'candidate_source_sha256':digest,'remote_published':False}))
    if not args.apply:return 0
    if subprocess.check_output(['git','status','--porcelain'],cwd=ROOT,text=True).strip():
        raise SystemExit('Commit or discard local changes before promotion')
    old='1.3.0-rc.1';new='1.3.0'
    paths=[ROOT/name for name in ('manifest.json','Panel.qml','BarWidget.qml')]
    originals={path:path.read_bytes() for path in paths}
    try:
        for path in paths:
            text=path.read_text()
            if text.count(old)!=1:raise ValueError('Version marker mismatch: '+path.name)
            path.write_text(text.replace(old,new))
        result=subprocess.run([sys.executable,'-B','qa/qualify.py','--native','--report-dir','reports/stable-qualification'],cwd=ROOT)
        if result.returncode:raise ValueError('Stable metadata requalification failed')
        stable=source_digest(ROOT)[0]
        atomic_json(ROOT/'reports/promotion.json',{'status':'passed','candidate_source_sha256':digest,'stable_source_sha256':stable,'finished_at':utc_now(),'changes':['manifest.json','Panel.qml','BarWidget.qml'],'remote_published':False})
        subprocess.run(['git','add','manifest.json','Panel.qml','BarWidget.qml'],cwd=ROOT,check=True)
        subprocess.run(['git','commit','-m','release: qualify OWEE 1.3.0'],cwd=ROOT,check=True)
        subprocess.run(['git','tag','v1.3.0'],cwd=ROOT,check=True)
    except Exception:
        for path,data in originals.items():path.write_bytes(data)
        raise
    return 0


if __name__=='__main__':sys.exit(main())
