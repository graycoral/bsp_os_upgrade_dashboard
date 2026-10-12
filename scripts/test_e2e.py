"""Run browser regressions against a fresh runtime, never a previously running API."""
import os
import json
from uuid import uuid4
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

root = Path(__file__).resolve().parents[1]
reports = root / '.local-reports'
reports.mkdir(exist_ok=True)
port = int(os.environ.get('BSP_E2E_PORT', '8766'))
# Fail before starting processes if another service owns the selected port.
with socket.socket() as probe:
    probe.bind(('127.0.0.1', port))
runtime = Path(tempfile.mkdtemp(prefix='e2e-run-', dir=reports))
env = dict(os.environ, BSP_E2E_RUNTIME=str(runtime), BSP_E2E_PORT=str(port), BSP_INSTANCE_ID=uuid4().hex)
api_log = (runtime / 'api.log').open('w')
worker_log = (runtime / 'worker.log').open('w')
processes = []
try:
    api = subprocess.Popen([sys.executable, 'scripts/serve.py', '--runtime', str(runtime), '--port', str(port)],
                           cwd=root, stdout=api_log, stderr=api_log, env=env)
    processes.append(api)
    worker = subprocess.Popen([sys.executable, '-m', 'backend.worker.main', '--runtime', str(runtime)],
                              cwd=root, stdout=worker_log, stderr=worker_log)
    processes.append(worker)
    for _ in range(40):
        if api.poll() is not None or worker.poll() is not None:
            raise RuntimeError(f'Isolated API/worker stopped; inspect {runtime}')
        try:
            # Match this run's process identifier; it is not an access credential.
            with urllib.request.urlopen(f'http://127.0.0.1:{port}/api/v1/health', timeout=1) as response:
                if json.load(response).get('instance_id') != env['BSP_INSTANCE_ID']:
                    raise RuntimeError('The port belongs to another API instance')
                break
        except OSError:
            time.sleep(.25)
    else:
        raise RuntimeError(f'Isolated API did not start; inspect {runtime}')
    result = subprocess.run(['npx', 'playwright', 'test'], cwd=root / 'apps/web', env=env)
    sys.exit(result.returncode)
finally:
    for process in reversed(processes):
        process.terminate()
        try:
            process.wait(timeout=8)
        except subprocess.TimeoutExpired:
            process.kill(); process.wait()
    api_log.close(); worker_log.close()
