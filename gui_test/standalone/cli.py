"""Detached local service with HTTP identity checks, no PID-based process killing."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import urllib.request
from gui_test.core.reporting import export
from gui_test.runtime import make_manager
from gui_test.core.models import digest


def main():
    p = argparse.ArgumentParser()
    p.add_argument('command', choices=['start', 'serve', 'status', 'stop', 'restart', 'export'])
    p.add_argument('--runtime', default=str(Path.home() / '.gui-test'))
    p.add_argument('--port', type=int, default=8767)
    p.add_argument('--run-id')
    p.add_argument('--format', choices=['json','csv','html','pdf','logs'], default='json')
    p.add_argument('--output')
    args = p.parse_args()
    root = Path(args.runtime).resolve(); root.mkdir(parents=True, exist_ok=True)
    if args.command == 'export':
        if not args.run_id or not args.output:
            p.error('export requires --run-id and --output')
        data, _ = export(make_manager(root, 'standalone').get(args.run_id), args.format)
        Path(args.output).write_bytes(data)
        return
    if args.command == 'serve':
        from gui_test.standalone.server import create_app, ProcessLock
        import uvicorn
        app = create_app(root)
        # The per-service shutdown marker is local only, never a public API.
        marker = root / 'stop-request'
        marker.unlink(missing_ok=True)
        server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=args.port, proxy_headers=False))
        import threading
        def monitor():
            while not server.should_exit:
                if marker.exists():
                    server.should_exit = True
                    marker.unlink(missing_ok=True)
                    return
                time.sleep(.2)
        # Ensure one service process per runtime even before opening a network port.
        with ProcessLock(root / 'service.lock'):
            threading.Thread(target=monitor, daemon=True).start()
            server.run()
        return
    def status():
        try:
            with urllib.request.urlopen(f'http://127.0.0.1:{args.port}/api/v1/health',timeout=1) as r:
                result = json.load(r)
            if result.get('mode') != 'standalone' or result.get('runtime_id') != digest(str(root)):
                raise SystemExit('Port belongs to a different service/runtime; choose the correct port and runtime')
            return result
        except (OSError, ValueError):
            return None
    if args.command == 'status':
        print(json.dumps(status() or {'status':'stopped'}, indent=2))
        return
    if args.command in {'stop','restart'}:
        (root / 'stop-request').write_text('stop', encoding='utf-8')
        for _ in range(100):
            if not status():
                break
            time.sleep(.1)
        if status():
            raise SystemExit('Service is still stopping; active TC is being collected. Do not force-restart.')
        if args.command == 'stop':
            print('Stopped. Run evidence remains in the runtime directory.')
            return
    if status():
        raise SystemExit('A standalone service already owns this port')
    kwargs = {'creationflags': subprocess.DETACHED_PROCESS | subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == 'nt' else {'start_new_session':True}
    with (root/'service.log').open('ab') as log:
        child = subprocess.Popen([sys.executable,'-m','gui_test.standalone.cli','serve','--runtime',str(root),'--port',str(args.port)],
                                 stdin=subprocess.DEVNULL, stdout=log, stderr=log, **kwargs)
    for _ in range(60):
        if child.poll() is not None:
            raise SystemExit('Service exited; inspect service.log')
        if status():
            print(f'GUI Test ready: http://127.0.0.1:{args.port}')
            return
        time.sleep(.1)
    raise SystemExit('Service readiness timeout; inspect service.log')


if __name__ == '__main__':
    main()
