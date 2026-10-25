"""Exercise the shared UI against a standalone service in a fresh local runtime."""
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

root=Path(__file__).resolve().parents[2]
reports=root/'.local-reports';reports.mkdir(exist_ok=True)
runtime=Path(tempfile.mkdtemp(prefix='gui-standalone-e2e-',dir=reports))
with socket.socket() as probe:
    probe.bind(('127.0.0.1',0));port=probe.getsockname()[1]
with (runtime/'server.log').open('w') as log:
    process=subprocess.Popen([sys.executable,'-m','gui_test.standalone.server','--runtime',str(runtime),'--port',str(port)],cwd=root,stdout=log,stderr=log)
    try:
        for _ in range(80):
            if process.poll() is not None:raise RuntimeError('Standalone stopped; inspect server.log')
            try:
                with urllib.request.urlopen(f'http://127.0.0.1:{port}/api/v1/health',timeout=1):break
            except OSError:time.sleep(.1)
        else:raise RuntimeError('Standalone readiness timeout')
        env=dict(os.environ,GUI_TEST_STANDALONE='1',BSP_E2E_PORT=str(port))
        raise SystemExit(subprocess.call(['npx','playwright','test','gui-test.spec.ts'],cwd=root/'apps/web',env=env))
    finally:
        process.terminate()
        try:process.wait(timeout=10)
        except subprocess.TimeoutExpired:process.kill();process.wait()
