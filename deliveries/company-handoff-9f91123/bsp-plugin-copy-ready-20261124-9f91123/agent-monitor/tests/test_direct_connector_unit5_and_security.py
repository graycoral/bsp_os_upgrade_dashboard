"""Tests for Direct Connector Unit 5 & Unit 6 (Security): DirectConnectorProxy, OFFLINE_CACHED, Middleware Scopes, Latch Guard, Preview UI."""
import json
from pathlib import Path
import socket
import sys
import threading
import time

import pytest
import uvicorn
from fastapi.testclient import TestClient

from backend.api.main import create_app as create_monitor_app
from backend.gui_test.connector.preview import MockConnector
from backend.gui_test.connector.web import preview_app
from backend.gui_test.core.shared_settings_store import SharedSettingsStore
from backend.gui_test.execution.host import Host, create_app as create_host_app
from backend.gui_test.standalone.direct_connector_client import DirectConnectorClient
from backend.gui_test.standalone.integration import create_app as create_standalone_app


def _free_port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


def _start_live_host(tmp_path: Path):
    home = tmp_path / 'winhome'
    runtime = home / 'runtime'
    runtime.mkdir(parents=True, exist_ok=True)
    cfg = {
        'python': sys.executable,
        'boards': [{'host': 'WINPC', 'board_id': 'B1', 'com': 'COM3'}],
        'serial_transport': 'native',
        '_setup': {'server': '127.0.0.1', 'account': 'bsp', 'ssh_port': 22, 'remote_runner_port': 8771},
    }
    cfg_path = home / 'windows-runner.json'
    cfg_path.write_text(json.dumps(cfg), encoding='utf-8')
    host = Host(cfg, runtime, ports=lambda: {'COM3'}, config_path=cfg_path)
    app = create_host_app(host)
    port = _free_port()
    server = uvicorn.Server(uvicorn.Config(app, host='127.0.0.1', port=port, access_log=False, log_level='warning'))
    t = threading.Thread(target=server.run, daemon=True)
    t.start()
    import httpx
    for _ in range(50):
        try:
            if httpx.get(f'http://127.0.0.1:{port}/v1/identity', timeout=1.0).status_code == 200:
                break
        except Exception:
            time.sleep(0.05)
    return host, port, server, t


def test_agent_monitor_direct_proxy_online_offline_cached_and_latch_guard(tmp_path):
    host, port, server, thread = _start_live_host(tmp_path)
    mon_app = None
    try:
        mon_rt = tmp_path / 'monitor_rt'
        store = SharedSettingsStore(mon_rt)
        store.save_preferences({'preferred_connector_port': port})

        # Setup TC project on Linux for running a failing TC that triggers analysis latch
        tc_root = tmp_path / 'tcs'
        tc_root.mkdir()
        (tc_root / 't_fail.py').write_text("print('Test Result: FAIL'); import sys; sys.exit(1)\n", encoding='utf-8')
        s0 = store.read()
        store.save({
            'expected_revision': s0['revision'],
            'integration': s0['integration'] | {'tc_root': str(tc_root), 'source_roots': [str(tmp_path)]},
            'timeouts': {k: v for k, v in s0['timeouts'].items() if k != 'revision'},
        })
        store.save_command_profile('default', {'single': ['python', '{tc_path}', '--com', '{com_a}'], 'dual': ['python', '{tc_path}', '--a', '{com_a}', '--b', '{com_b}']})

        mon_app = create_monitor_app(mon_rt)
        with TestClient(mon_app, base_url='http://127.0.0.1:8766', client=('127.0.0.1', 5000)) as client:
            # 1. Live probe directly from Agent Monitor -> caches snapshot & sends peer/hello(agent_monitor)!
            st = client.get('/api/v1/gui-test/live/connector/direct/status')
            assert st.status_code == 200
            body = st.json()
            assert body['fresh'] is True
            assert body['live_status'] == 'ONLINE'
            assert body['runner_id'] == host.identity
            assert body['target_port'] == port

            # Arbitrary ?port= query parameter MUST be ignored on /direct/status and /direct/diagnostics (no port scan / cache pollution).
            st_ignored = client.get('/api/v1/gui-test/live/connector/direct/status?port=1').json()
            diag_ignored = client.get('/api/v1/gui-test/live/connector/direct/diagnostics?port=1').json()
            assert st_ignored['target_port'] == port and st_ignored['fresh'] is True
            assert diag_ignored['target_port'] == port and diag_ignored['fresh'] is True

            # Check linux-diagnostics endpoint directly.
            ldiag = client.get('/api/v1/gui-test/live/connector/direct/linux-diagnostics')
            assert ldiag.status_code == 200 and 'port_listener' in ldiag.json()

            # 2. Run failing TC via DirectConnectorClient -> analysis_latched=1 -> Monitor resume MUST return 409 ANALYSIS_LATCH_ACTIVE!
            dc = DirectConnectorClient(runtime_dir=mon_rt, connector_port=port)
            try:
                run = dc.start_run()
                run_id = run['run_id']
                latched = dc.watch_run(run_id, timeout_s=5.0)
                assert latched['analysis_latched'] is True
            finally:
                dc.close()

            # Missing X-Bsp-Client header blocked by dashboard middleware (403).
            no_hdr = client.post(f'/api/v1/gui-test/live/connector/direct/runs/{run_id}/resume', json={})
            assert no_hdr.status_code == 403

            # Cross-origin rejected (403).
            bad_origin = client.post(
                f'/api/v1/gui-test/live/connector/direct/runs/{run_id}/resume',
                headers={'Origin': 'http://evil.example', 'X-Bsp-Client': 'dashboard'},
                json={},
            )
            assert bad_origin.status_code == 403

            # Same-origin valid header hits latch guard -> 409 ANALYSIS_LATCH_ACTIVE!
            res = client.post(
                f'/api/v1/gui-test/live/connector/direct/runs/{run_id}/resume',
                headers={'Origin': 'http://127.0.0.1:8766', 'X-Bsp-Client': 'dashboard'},
                json={},
            )
            assert res.status_code == 409 and res.json()['code'] == 'ANALYSIS_LATCH_ACTIVE'

            # Cancel allowed via DirectConnectorProxy!
            can = client.post(
                f'/api/v1/gui-test/live/connector/direct/runs/{run_id}/cancel',
                headers={'Origin': 'http://127.0.0.1:8766', 'X-Bsp-Client': 'dashboard'},
                json={},
            )
            assert can.status_code == 200

            # Refresh online cache before shutting down Windows Host.
            assert client.get('/api/v1/gui-test/live/connector/direct/status').json()['fresh'] is True

            # 3. Stop Windows Host -> Agent Monitor MUST serve OFFLINE_CACHED with cached data + Linux diagnostics!
            server.should_exit = True
            thread.join(timeout=3.0)

            offline = client.get('/api/v1/gui-test/live/connector/direct/status')
            assert offline.status_code == 200
            off_json = offline.json()
            assert off_json['fresh'] is False
            assert off_json['live_status'] == 'OFFLINE_CACHED'
            assert off_json['runner_id'] == host.identity
            assert off_json['mutual_diagnostics']['code'] == 'CONNECTOR_TUNNEL_NOT_LISTENING'
    finally:
        if mon_app is not None:
            proxy = getattr(getattr(mon_app.state, 'gui_live_manager', None), 'direct_proxy', None)
            if proxy is not None:
                proxy.stop_background_probe()
        server.should_exit = True
        thread.join(timeout=3.0)
        host.close()


def test_standalone_security_middleware_enforces_scopes_and_csrf_on_direct_routes(tmp_path):
    rt = tmp_path / 'standalone_rt'
    app = create_standalone_app(rt, start_worker=False)
    with TestClient(app, base_url='http://127.0.0.1:8766', client=('127.0.0.1', 5000)) as client:
        # Unauthenticated direct mutation rejected (401).
        assert client.post('/api/v1/gui-test/live/connector/direct/rebind', json={}).status_code == 401

        # Non-browser loopback connector request to /direct/linux-diagnostics is allowed (both with and without X-Bsp-Service),
        # while browser Origin without session is rejected (401).
        assert client.get('/api/v1/gui-test/live/connector/direct/linux-diagnostics').status_code == 200
        assert client.get('/api/v1/gui-test/live/connector/direct/linux-diagnostics', headers={'X-Bsp-Service': 'plugin'}).status_code == 200
        assert client.get('/api/v1/gui-test/live/connector/direct/linux-diagnostics', headers={'Origin': 'http://127.0.0.1:8766'}).status_code == 401

        # Grant settings-only browser session (via plugin service identity)!
        health = client.get('/api/v1/health', headers={'X-Bsp-Service': 'plugin'}).json()
        svc_hdrs = {
            'X-Bsp-Service': 'plugin',
            'X-Bsp-Runtime-Id': health['runtime_id'],
            'X-Bsp-Package-Version': health['package_version'],
        }
        grant_s = client.post('/api/v1/gui-test/live/integration/browser-session', headers=svc_hdrs, json={'scopes': ['settings']}).json()
        ex = client.post(
            '/auth/session',
            headers={'Origin': 'http://127.0.0.1:8766'},
            data={'code': grant_s['bootstrap_code']},
            follow_redirects=False,
        )
        assert ex.status_code == 303
        me = client.get('/api/v1/gui-test/live/integration/browser-session').json()
        csrf = me['csrf_token']

        # Missing CSRF -> 403.
        r_nocsrf = client.put(
            '/api/v1/gui-test/live/connector/direct/preferences',
            headers={'Origin': 'http://127.0.0.1:8766', 'X-Bsp-Client': 'dashboard'},
            json={'preferred_connector_port': 8779},
        )
        assert r_nocsrf.status_code == 403

        # Valid settings scope + CSRF -> succeeds (200)!
        r_ok = client.put(
            '/api/v1/gui-test/live/connector/direct/preferences',
            headers={'Origin': 'http://127.0.0.1:8766', 'X-Bsp-Client': 'dashboard', 'X-Gui-Csrf': csrf},
            json={'preferred_connector_port': 8779},
        )
        assert r_ok.status_code == 200 and r_ok.json()['preferred_connector_port'] == 8779

        # Settings-only scope CANNOT call control mutation (/direct/reconnect-ssh) -> 403!
        r_ctrl_denied = client.post(
            '/api/v1/gui-test/live/connector/direct/reconnect-ssh',
            headers={'Origin': 'http://127.0.0.1:8766', 'X-Bsp-Client': 'dashboard', 'X-Gui-Csrf': csrf},
            json={},
        )
        assert r_ctrl_denied.status_code == 403


def test_windows_preview_web_ui_supports_direct_actions_and_3axis_status(tmp_path):
    app = preview_app(MockConnector(tmp_path), 'http://127.0.0.1:8774')
    with TestClient(app, base_url='http://127.0.0.1:8774', client=('127.0.0.1', 5000)) as client:
        ticket_url = app.state.browser_ui.ticket()['url']
        ticket = ticket_url.split('#ticket=')[1]
        sess_r = client.post(
            app.state.browser_ui.prefix + '/session',
            headers={'Origin': 'http://127.0.0.1:8774'},
            json={'ticket': ticket},
        )
        assert sess_r.status_code == 200, sess_r.text
        csrf = sess_r.json()['csrf']

        st = client.get(app.state.browser_ui.prefix + '/api/status').json()
        assert st['stages']['agent_monitor'] == 'OPTIONAL_OFFLINE'
        assert 'overall' in st['stages']

        r1 = client.post(
            app.state.browser_ui.prefix + '/api/action',
            headers={'Origin': 'http://127.0.0.1:8774', 'X-Connector-CSRF': csrf},
            json={'action': 'verify-connection', 'payload': {}},
        )
        assert r1.status_code == 200 and r1.json()['verified'] is True

        r2 = client.post(
            app.state.browser_ui.prefix + '/api/action',
            headers={'Origin': 'http://127.0.0.1:8774', 'X-Connector-CSRF': csrf},
            json={'action': 'reconnect-ssh', 'payload': {}},
        )
        assert r2.status_code == 200 and r2.json()['reconnected'] is True

        r3 = client.post(
            app.state.browser_ui.prefix + '/api/action',
            headers={'Origin': 'http://127.0.0.1:8774', 'X-Connector-CSRF': csrf},
            json={'action': 'restart-host', 'payload': {}},
        )
        assert r3.status_code == 200 and r3.json()['ssh_preserved'] is True

        # Check view.mjs renders new controls and PASSED/FAILED -> PASS/FAIL normalization cleanly.
        view_js = client.get(app.state.browser_ui.prefix + '/view.mjs').text
        assert '연결 확인' in view_js and 'SSH 재연결' in view_js and 'agent_monitor' in view_js
        assert 'normTcState' in view_js and "s==='PASSED'?'PASS':s==='FAILED'?'FAIL'" in view_js

    mirror_tsx = (Path(__file__).resolve().parents[1] / 'packages' / 'gui-test-ui' / 'src' / 'ConnectorMirror.tsx').read_text(encoding='utf-8')
    assert 'preferDirect=Boolean(directStatus&&(directStatus.fresh||!snapshot?.inventory?.runner_id))' in mirror_tsx
    assert 'useDirectTests=preferDirect?' in mirror_tsx
    assert "value==='PASSED'?'PASS':value==='FAILED'?'FAIL'" in mirror_tsx


def test_manager_catalog_falls_back_to_shared_tc_root_and_test_page_toggle(tmp_path):
    from backend.gui_test.core.shared_settings_store import SharedSettingsStore
    from backend.gui_test.runtime import make_manager

    rt = tmp_path / 'rt'
    tc_root = tmp_path / 'tcs'
    tc_root.mkdir()
    (tc_root / 'sample_tc.py').write_text("print('Test Result: PASS')\n", encoding='utf-8')

    store = SharedSettingsStore(rt)
    s0 = store.read()
    store.save({
        'expected_revision': s0['revision'],
        'integration': s0['integration'] | {'tc_root': str(tc_root), 'source_roots': [str(tmp_path)]},
        'timeouts': {k: v for k, v in s0['timeouts'].items() if k != 'revision'},
    })

    mgr = make_manager(rt, 'integration')
    catalog = mgr.catalog('shared')
    assert [t['id'] for t in catalog['tests']] == ['sample_tc.py']

    test_page = (Path(__file__).resolve().parents[1] / 'packages' / 'gui-test-ui' / 'src' / 'TestPage.tsx').read_text(encoding='utf-8')
    assert '전체 TC 보기' in test_page
    assert 'effectiveModuleScope' in test_page
    assert '플러그인 보드 커넥터 자율 실행' in test_page


def test_delete_job_endpoint_and_overall_progress_box(tmp_path):
    from fastapi.testclient import TestClient
    from backend.api.main import create_app

    app = create_app(tmp_path / 'rt')
    with TestClient(app, base_url='http://127.0.0.1:8766', client=('127.0.0.1', 5000)) as client:
        hdrs = {'Origin': 'http://127.0.0.1:8766', 'X-Bsp-Client': 'dashboard'}
        created = client.post('/api/v1/jobs', headers=hdrs | {'Idempotency-Key': 'del-job-1'}, json={'title': 'Del Job', 'mode': 'linux'})
        assert created.status_code == 202
        job_id = created.json()['job_id']

        # Safe delete succeeds when no stage is RUNNING/UNKNOWN or leased.
        deleted = client.delete(f'/api/v1/jobs/{job_id}', headers=hdrs)
        assert deleted.status_code == 200 and deleted.json()['deleted'] is True
        assert client.get(f'/api/v1/jobs/{job_id}').status_code == 404

    main_tsx = (Path(__file__).resolve().parents[1] / 'apps' / 'web' / 'src' / 'main.tsx').read_text(encoding='utf-8')
    assert '작업 삭제' in main_tsx
    assert '작업 재실행' in main_tsx
    assert 'overall-progress-box' in main_tsx


def test_connector_run_rerun_clones_completed_run(tmp_path):
    import zipfile
    import hashlib
    from fastapi.testclient import TestClient
    from backend.gui_test.execution.host import Host, create_app as create_host_app
    from backend.gui_test.execution import source_snapshots

    home = tmp_path / 'win'
    rt = home / 'runtime'
    rt.mkdir(parents=True)
    cfg_path = home / 'windows-runner.json'
    cfg = {'python': sys.executable, 'boards': [{'host': 'WINPC', 'board_id': 'B1', 'com': 'COM3'}], 'serial_transport': 'native'}
    cfg_path.write_text(json.dumps(cfg), encoding='utf-8')
    host = Host(cfg, rt, ports=lambda: {'COM3'}, config_path=cfg_path)
    app = create_host_app(host)
    try:
        src_dir = tmp_path / 'src'
        src_dir.mkdir()
        (src_dir / 't1.py').write_text("print('Test Result: PASS')\n", encoding='utf-8')
        files = {'t1.py': (src_dir / 't1.py').read_bytes()}
        manifest = source_snapshots.manifest(files, {'kind': 'local', 'path': str(src_dir)}, {})
        zpath = tmp_path / 'src.zip'
        with zipfile.ZipFile(zpath, 'w') as zf:
            zf.writestr(source_snapshots.MANIFEST, json.dumps(manifest, sort_keys=True))
            zf.writestr('t1.py', files['t1.py'])

        with TestClient(app, base_url='http://127.0.0.1:8772', client=('127.0.0.1', 5000)) as client:
            raw = zpath.read_bytes()
            up = client.put(f"/v1/source-snapshots/{manifest['snapshot_id']}", content=raw,
                            headers={'Content-Type': 'application/zip', 'Content-Length': str(len(raw))})
            assert up.status_code == 200
            cmd = {'single': ['python', '{tc_path}', '--com', '{com_a}'], 'dual': ['python', '{tc_path}', '--a', '{com_a}', '--b', '{com_b}']}
            created = client.post('/v1/connector-runs', headers={'Idempotency-Key': 'orig-1'}, json={
                'execution_mode': 'tc_only',
                'connection': {'a': {'host': 'WINPC', 'board_id': 'B1', 'com': 'COM3'}},
                'source_snapshot_id': manifest['snapshot_id'],
                'source_revision': manifest['source_revision'],
                'command_snapshot': {'name': 'default', 'revision': hashlib.sha256(json.dumps(cmd, sort_keys=True).encode()).hexdigest(), 'template': cmd},
                'tests': [{'step_index': 0, 'tc_id': 't1.py', 'path': 't1.py', 'kind': 'Single'}],
            })
            assert created.status_code == 201
            run1_id = created.json()['run_id']
            deadline = time.monotonic() + 5.0
            while time.monotonic() < deadline:
                cur = client.get(f'/v1/connector-runs/{run1_id}').json()
                if cur['state'] == 'COMPLETED':
                    break
                time.sleep(0.05)
            assert cur['state'] == 'COMPLETED'

            rerun = client.post(f'/v1/connector-runs/{run1_id}/rerun', headers={'Idempotency-Key': 'rerun-1'})
            assert rerun.status_code == 201
            run2 = rerun.json()
            assert run2['run_id'] != run1_id
            assert run2['parent_run_id'] == run1_id
    finally:
        host.close()


def test_direct_proxy_and_api_validate_run_ids_and_log_stream(tmp_path):
    from backend.gui_test.connector.direct_proxy import DirectConnectorProxy
    from backend.gui_test.core.models import TestError

    rt = tmp_path / 'rt'
    app = create_standalone_app(rt, start_worker=False)
    proxy = app.state.manager.direct_proxy
    forwarded = []
    proxy._request_windows = lambda method, path, **kw: forwarded.append((method, path)) or {'ok': True}

    bad_ids = ['../identity', 'abc', 'g' * 32, 'a' * 31, 'a' * 32 + '?x=1']
    for bad in bad_ids:
        for fn in (
            lambda b=bad: proxy.get_run(b),
            lambda b=bad: proxy.pause_run(b),
            lambda b=bad: proxy.resume_run(b),
            lambda b=bad: proxy.cancel_run(b),
            lambda b=bad: proxy.reconcile_run(b, {'action': 'MARK_ABORTED'}),
            lambda b=bad: proxy.read_logs(b, 'b' * 32, stream='stdout'),
            lambda b=bad: proxy.read_logs('a' * 32, b, stream='stdout'),
        ):
            with pytest.raises(TestError) as exc_info:
                fn()
            assert exc_info.value.status == 422
            assert exc_info.value.code == 'INVALID_ID'

    for bad_stream in ('secret', 'stdout&evil=1', '../events', ''):
        with pytest.raises(TestError) as exc_info:
            proxy.read_logs('a' * 32, 'b' * 32, stream=bad_stream)
        assert exc_info.value.status == 422
        assert exc_info.value.code == 'INVALID_STREAM'

    assert forwarded == []

    with TestClient(app, base_url='http://127.0.0.1:8766', client=('127.0.0.1', 5000)) as client:
        # Obtain valid control+settings browser session for POST mutation checks.
        health = client.get('/api/v1/health', headers={'X-Bsp-Service': 'plugin'}).json()
        svc_hdrs = {
            'X-Bsp-Service': 'plugin',
            'X-Bsp-Runtime-Id': health['runtime_id'],
            'X-Bsp-Package-Version': health['package_version'],
        }
        grant = client.post('/api/v1/gui-test/live/integration/browser-session', headers=svc_hdrs, json={'scopes': ['control']}).json()
        client.post('/auth/session', headers={'Origin': 'http://127.0.0.1:8766'}, data={'code': grant['bootstrap_code']}, follow_redirects=False)
        csrf = client.get('/api/v1/gui-test/live/integration/browser-session').json()['csrf_token']
        hdrs = {'Origin': 'http://127.0.0.1:8766', 'X-Bsp-Client': 'dashboard', 'X-Gui-Csrf': csrf}

        assert client.get('/api/v1/gui-test/live/connector/direct/runs/not-a-hex-id').status_code == 422
        assert client.post('/api/v1/gui-test/live/connector/direct/runs/not-a-hex-id/pause', headers=hdrs, json={}).status_code == 422
        assert client.post('/api/v1/gui-test/live/connector/direct/runs/not-a-hex-id/resume', headers=hdrs, json={}).status_code == 422
        assert client.post('/api/v1/gui-test/live/connector/direct/runs/not-a-hex-id/cancel', headers=hdrs, json={}).status_code == 422
        assert client.post('/api/v1/gui-test/live/connector/direct/runs/not-a-hex-id/reconcile', headers=hdrs, json={}).status_code == 422
        assert client.get(f"/api/v1/gui-test/live/connector/direct/runs/{'a' * 32}/attempts/bad-attempt/logs?stream=stdout").status_code == 422
        assert client.get(f"/api/v1/gui-test/live/connector/direct/runs/{'a' * 32}/attempts/{'b' * 32}/logs?stream=evil").status_code == 422
        assert forwarded == []

        # Valid IDs and stream forward cleanly.
        assert client.get(f"/api/v1/gui-test/live/connector/direct/runs/{'a' * 32}/attempts/{'b' * 32}/logs?stream=uart").status_code == 200
        assert forwarded == [('GET', f"/v1/connector-runs/{'a' * 32}/attempts/{'b' * 32}/logs?stream=uart&offset=0&limit=65536")]
