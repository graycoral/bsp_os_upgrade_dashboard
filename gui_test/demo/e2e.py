"""Headless end-to-end demonstration through the real manager, worker and SQLite.

All addresses, board names, processes and results are synthetic.
"""
import argparse
import json
from pathlib import Path
import tempfile
import time
from gui_test.core.models import uid
from gui_test.core.worker import Worker
from gui_test.runtime import make_manager


def run_scenario(root, scenario, integrated=False):
    m=make_manager(root,'dashboard' if integrated else 'standalone')
    job=m.dashboard.create(uid()) if integrated else None
    catalog=m.catalog()
    req={'tc_ids':[t['id'] for t in catalog['tests']], 'source_revision':catalog['revision'],
         'connection':{'a':m.boards.boards()[0],'b':m.boards.boards()[1]},'scenario':scenario,'speed':20,
         'job_id':job['id'] if job else None}
    r=m.start(uid(),'demo-cli',req)
    worker=Worker(m)
    try:
        deadline=time.monotonic()+15
        while time.monotonic()<deadline:
            worker.tick();r=m.get(r['id'])
            if r['state'] in {'PAUSED','UNKNOWN'}:
                r=m.act(r['id'],uid(),'demo-cli',r['version'],'demo-recover')
                r=m.act(r['id'],uid(),'demo-cli',r['version'],'resume')
            if r['state']=='COMPLETED' and r['sync']['status'] in {'SUCCEEDED','NOT_LINKED'}:
                expected='FAIL' if scenario=='fail' else 'PASS'
                assert r['overall_result']==expected
                return {'scenario':scenario,'mode':m.mode,'run_id':r['id'],'result':r['overall_result'],
                        'attempts':len(r['attempts']),'sync':r['sync']['status'],'simulation':True}
            time.sleep(.01)
        raise RuntimeError(f'Scenario did not finish: {scenario} / {r["state"]} / {r["sync"]}')
    finally:worker.close()


def main():
    p=argparse.ArgumentParser();p.add_argument('--output');p.add_argument('--dashboard',action='store_true');args=p.parse_args()
    scenarios=['pass','fail','disconnect','timeout','unknown']+(['sync-failure','sync-lost-response'] if args.dashboard else [])
    with tempfile.TemporaryDirectory(prefix='gui-test-demo-') as temp:
        results=[run_scenario(Path(temp)/s,s,args.dashboard) for s in scenarios]
    content=json.dumps({'simulation':True,'passed':len(results),'scenarios':results},indent=2)
    if args.output:Path(args.output).write_text(content,encoding='utf-8')
    print(content)


if __name__=='__main__':main()
