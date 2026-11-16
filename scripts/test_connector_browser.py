"""Browser regressions use a fresh mock fixture, never a running company service."""
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import time
import urllib.request


def main():
    root=Path(__file__).resolve().parents[1]
    reports=root/'.local-reports/20261114-connector-web-review'/('browser-'+str(time.time_ns()));reports.mkdir(parents=True,exist_ok=True)
    print('Mock browser evidence:',reports,flush=True)
    with socket.socket() as listener:
        listener.bind(('127.0.0.1',0));port=listener.getsockname()[1]
    env=dict(os.environ,CONNECTOR_FIXTURE_KEY=secrets.token_urlsafe(32),BSP_E2E_PORT=str(port))
    with (reports/'browser-server.log').open('w') as log:
        process=subprocess.Popen([sys.executable,str(root/'tests/connector_browser_fixture.py'),'--port',str(port)],cwd=root,env=env,stdout=log,stderr=log)
        try:
            for _ in range(80):
                if process.poll() is not None:raise RuntimeError('Mock fixture stopped; inspect browser-server.log')
                try:
                    # A denied unauthenticated route still proves this exact fixture is ready.
                    urllib.request.urlopen(f'http://127.0.0.1:{port}/fixture-ticket',timeout=1)
                except urllib.error.HTTPError as exc:
                    if exc.code==403:break
                except OSError:pass
                time.sleep(.1)
            else:raise RuntimeError('Mock fixture readiness timeout')
            return subprocess.call(['npx.cmd' if os.name=='nt' else 'npx','playwright','test','connector-web.spec.ts',
                                    '--reporter=line','--output',str(reports/'artifacts')],cwd=root/'apps/web',env=env)
        finally:
            process.terminate()
            try:process.wait(timeout=10)
            except subprocess.TimeoutExpired:process.kill();process.wait()


if __name__=='__main__':raise SystemExit(main())
