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
    args = p.parse_args()
    app = create_app(args.runtime)
    proxy = getattr(getattr(app.state, 'gui_live_manager', None), 'direct_proxy', None)
    if proxy is not None:
        proxy.start_background_probe(10.0)
    print(f'Open http://127.0.0.1:{args.port} · local dashboard ready', flush=True)
    try:
        uvicorn.run(app, host='127.0.0.1', port=args.port, proxy_headers=False)
    finally:
        if proxy is not None:
            proxy.stop_background_probe()
