"""Real loopback API plus supervisor loop; all board/process children are fixtures."""
import importlib.util
import json
import signal
import socket
import sqlite3
import threading
import time
from pathlib import Path

import pytest
import uvicorn

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize('state,integration', [('PAUSED', False), ('QUEUED', False), ('PAUSED', True), ('PAUSED', 'batch')])
@pytest.mark.parametrize('configured', [False, True])
def test_reset_live_paused_reservations_through_existing_api_and_supervisor(tmp_path, monkeypatch, state, integration, configured):
    monkeypatch.syspath_prepend(str(ROOT/'apps/agent-monitor'))
    spec = importlib.util.spec_from_file_location('reset_live_manager', ROOT/'apps/agent-monitor/manage.py')
    manager = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(manager)
    from backend.api.main import create_app
    from backend.gui_test.runtime import make_manager
    home = tmp_path/'home'
    runtime = manager.bind_runtime(home, tmp_path/'runtime')
    runtime.mkdir(parents=True, exist_ok=True)
    if configured:
        (runtime/'gui-test.json').write_text('{"runner":"registered"}')
    app = create_app(runtime)
    # Create a full Run via the normal entry point, then transfer its frozen
    # fixture into the live store. No runner executes a TC or contacts a board.
    fixture = make_manager(tmp_path/'fixture', 'standalone')
    catalog = fixture.catalog()
    tc = next(t for t in catalog['tests'] if t['kind'] == 'Single')
    run = fixture.start('fixture', 'bsp-upgrade', {'tc_ids':[tc['id']], 'source_revision':catalog['revision'],
                        'connection':{'a':fixture.boards.boards()[0]}})
    live = app.state.gui_live_manager
    run.update(state=state, simulation=False)
    if integration:
        run['integration'] = {'contract_version':'bsp-upgrade-integration-v1', 'phase':'PREPARING',
                              'retry_policy':'fail-stop-analysis-v1'}
    if integration == 'batch':
        run['integration'].update(phase='TESTING', batch={'state':'READY','batch_id':'fixture-batch'})
        monkeypatch.setattr(live.runner,'finish_integration',lambda batch:{'state':'RELEASED','batch_id':batch['batch_id']})
    with live.store.transaction() as connection:
        connection.execute('INSERT INTO runs VALUES(?,?)', (run['id'],json.dumps(run)))
        connection.executemany('INSERT INTO reservations VALUES(?,?,?)',
                               [('board',run['id'],run['lease_token']),('console',run['id'],run['lease_token'])])
    listener = socket.socket()
    listener.bind(('127.0.0.1',0))
    port = listener.getsockname()[1]
    children, failures = [], []
    ready = threading.Event()
    stopped = threading.Event()
    release = home/'releases/fixed'
    monkeypatch.setattr(manager,'current',lambda home:{'path':str(release),'release':'a'*64})
    monkeypatch.setattr(manager.signal,'signal',lambda *args:signal.SIG_DFL)

    class Child:
        def __init__(self, kind):
            self.kind, self.returncode = kind, None
            if kind == 'worker':
                self.ownership = manager.lock(runtime/'worker.lock')
                self.ownership.__enter__()
                self.drained = threading.Event()
                def finalize():
                    while not self.drained.wait(.02):
                        for current in live.store.all():
                            meta = current.get('integration') or {}
                            if meta.get('pending_terminal_state') and not meta.get('batch_released'):
                                live.integration.finalize_run(current['id'])
                self.thread = threading.Thread(target=finalize, daemon=True)
                self.thread.start()
            else:
                self.server = uvicorn.Server(uvicorn.Config(app, log_level='error', lifespan='off'))
                self.thread = threading.Thread(target=self.server.run, kwargs={'sockets':[listener.dup()]}, daemon=True)
                self.thread.start()
                deadline = time.monotonic()+5
                while not self.server.started:
                    if time.monotonic()>deadline: raise RuntimeError('fixture API did not start')
                    time.sleep(.01)
                ready.set()

        def poll(self): return self.returncode

        def send_signal(self, value):
            assert value == signal.SIGINT
            if self.kind == 'api': self.server.should_exit = True
            else:
                self.drained.set()
                self.returncode = 0

        def wait(self, timeout=None):
            if self.kind == 'api':
                self.thread.join(timeout or 5)
                assert not self.thread.is_alive()
            else:
                self.thread.join(5)
                assert not self.thread.is_alive()
                self.ownership.__exit__(None,None,None)
            self.returncode = 0
            return 0

    def launch(argv, **kwargs):
        for name in ['AGENT_MONITOR_INSTANCE','AGENT_MONITOR_RELEASE']:
            monkeypatch.setenv(name, kwargs['env'][name])
        child = Child('worker' if 'backend.worker.main' in argv else 'api')
        children.append(child)
        return child
    monkeypatch.setattr(manager.subprocess,'Popen',launch)

    def supervise():
        try: manager.serve(home,port)
        except BaseException as exc: failures.append(exc)
        finally: stopped.set()
    owner = threading.Thread(target=supervise, daemon=True)
    owner.start()
    try:
        assert ready.wait(5), failures
        assert manager.active(home) and manager.has_work(runtime)
        # This calls the real HTTP routes and unchanged has_work stop gate.
        result = manager.reset_runtime(home)
        assert result['state'] == 'RESET'
        assert stopped.wait(5) and not failures
        assert live.store.all() == []
        assert not manager.has_work(runtime)
        relative = live.store.path.relative_to(runtime)
        with sqlite3.connect(Path(result['backup']['path'])/relative) as connection:
            saved = json.loads(connection.execute('SELECT data FROM runs').fetchone()[0])
            assert saved['state'] == state and saved['simulation'] is False
            assert connection.execute('SELECT COUNT(*) FROM reservations').fetchone()[0] == 2
        assert len(list((home/'backups').iterdir())) == 1
    finally:
        # Cleanup applies only to this test's private runtime, even on baseline failure.
        with live.store.transaction() as connection:
            connection.execute('DELETE FROM runs')
            connection.execute('DELETE FROM reservations')
        if manager.active(home): manager.stop(home)
        owner.join(5)
        listener.close()
        assert not owner.is_alive(), failures
