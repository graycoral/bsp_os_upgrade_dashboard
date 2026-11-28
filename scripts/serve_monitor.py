"""Run the API; run the worker separately so closing the browser never stops work."""
import argparse
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import uvicorn
from backend.api.main import create_app

if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--port', type=int, default=8766)
    p.add_argument('--runtime', default='.runtime')
    p.add_argument('--sharing-monitor-id')
    p.add_argument('--sharing-monitor-key-file')
    transport = p.add_mutually_exclusive_group()
    transport.add_argument('--sharing-host-socket')
    transport.add_argument('--trust-protected-loopback', action='store_true', default=None)
    p.add_argument('--sharing-host-socket-owner-uid', type=int)
    p.add_argument('--connector-port', type=int)
    args = p.parse_args()
    app = create_app(args.runtime, sharing_monitor_id=args.sharing_monitor_id, connector_port=args.connector_port,
                     sharing_monitor_key_file=args.sharing_monitor_key_file, sharing_host_socket=args.sharing_host_socket,
                     sharing_host_socket_owner_uid=args.sharing_host_socket_owner_uid,
                     trust_protected_loopback=args.trust_protected_loopback)
    proxy = getattr(getattr(app.state, 'gui_live_manager', None), 'direct_proxy', None)
    if proxy is not None:
        proxy.start_background_probe(10.0)
    if hasattr(app.state, 'engine'):
        print(f'Open http://127.0.0.1:{args.port} · local dashboard ready', flush=True)
    else:
        print(f'Shared task Monitor ready on loopback port {args.port}', flush=True)
    try:
        uvicorn.run(app, host='127.0.0.1', port=args.port, proxy_headers=False, access_log=hasattr(app.state, 'engine'))
    finally:
        if proxy is not None:
            proxy.stop_background_probe()
