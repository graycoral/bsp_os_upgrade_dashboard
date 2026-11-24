"""Tests for Direct Connector Unit 3: ConnectorRunExecutor, fail-stop latch, RETRY/REPREPARE, UNKNOWN, retention."""
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import time
import zipfile

import pytest
from fastapi.testclient import TestClient

from backend.gui_test.core.models import digest
from backend.gui_test.execution import installer_snapshots, retention, source_snapshots
from backend.gui_test.execution.connector_runs import resolve_step_timeout
from backend.gui_test.execution.host import Host, create_app


def _build_source_zip(tmp_path: Path, name: str = 'src.zip', *, scripts: dict[str, str], metadata: dict | None = None) -> tuple[Path, str, str]:
    files = {rel: body.encode('utf-8') for rel, body in scripts.items()}
    manifest = source_snapshots.manifest(files, {'kind': 'local'}, metadata or {})
    zpath = tmp_path / name
    with zipfile.ZipFile(zpath, 'w') as zf:
        zf.writestr(source_snapshots.MANIFEST, json.dumps(manifest, sort_keys=True))
        for rel, raw in files.items():
            zf.writestr(rel, raw)
    return zpath, manifest['snapshot_id'], manifest['source_revision']


def _build_installer_zip(tmp_path: Path, name: str = 'inst.zip') -> tuple[Path, str, bytes]:
    payload_img = b'FLASH_IMAGE_DATA_' * 2048
    img_sha = hashlib.sha256(payload_img).hexdigest()
    bat_bytes = b'@echo FLASH OK\r\n'
    bat_sha = hashlib.sha256(bat_bytes).hexdigest()
    base = {
        'format': 'installer_snapshot_v1',
        'batch': 'flash_all.bat',
        'files': {
            'flash_all.bat': {'size': len(bat_bytes), 'sha256': bat_sha},
            'boot.img': {'size': len(payload_img), 'sha256': img_sha},
        },
    }
    snap_id = digest(base)
    manifest = base | {'snapshot_id': snap_id}
    zpath = tmp_path / name
    with zipfile.ZipFile(zpath, 'w') as zf:
        zf.writestr(installer_snapshots.MANIFEST, json.dumps(manifest, sort_keys=True))
        zf.writestr('flash_all.bat', bat_bytes)
        zf.writestr('boot.img', payload_img)
    raw = zpath.read_bytes()
    return zpath, snap_id, hashlib.sha256(raw).hexdigest(), raw


def _make_flash_config(tmp_path: Path, *, enabled: bool = True):
    fb = tmp_path / 'fastboot.exe'
    fb.write_text('stub', encoding='utf-8')
    bat_sha = hashlib.sha256(b'@echo FLASH OK\r\n').hexdigest()
    obs = {
        'port': 'COM9',
        'baudrate': 115200,
        'rx_only_confirmed': True,
        'control_lines_isolated': True,
        'panic_signatures': ['Kernel panic'],
        'boot_signatures': ['Booting Linux'],
        'login_markers': ['login:'],
    }
    profile = {
        'enabled': enabled,
        'fastboot': str(fb),
        'batch_sha256': bat_sha,
        'success_marker': 'FLASH_SUCCESS',
        'failure_markers': ['FAILED'],
        'console_timeout': 5,
        'fastboot_timeout': 5,
        'flash_timeout': 10,
        'boot_timeout': 5,
        'boards': {
            'B1': {
                'serial': 'SER-B1',
                'com': 'COM3',
                'baudrate': 115200,
                'line_ending': 'cr',
                'lkshell_prompt': 'lkshell>',
                'boot_marker': 'BOOT_READY',
                'login_prompt': 'login:',
                'login_steps': [],
                'observer': obs,
            }
        },
    }
    return {'profiles': {'default': profile}}


def _setup_host(tmp_path: Path, *, with_flash: bool = False):
    home = tmp_path / 'winhome'
    runtime = home / 'runtime'
    runtime.mkdir(parents=True, exist_ok=True)
    cfg = {
        'python': sys.executable,
        'boards': [
            {'host': 'WINPC', 'board_id': 'B1', 'com': 'COM3'},
            {'host': 'WINPC', 'board_id': 'B2', 'com': 'COM4'},
        ],
        'serial_transport': 'native',
        'flashing': _make_flash_config(tmp_path) if with_flash else {'profiles': {}},
    }
    cfg_path = home / 'windows-runner.json'
    cfg_path.write_text(json.dumps(cfg), encoding='utf-8')
    host = Host(cfg, runtime, ports=lambda: {'COM3', 'COM4'}, config_path=cfg_path)
    return home, runtime, host, create_app(host)


def _upload_source(client: TestClient, zpath: Path, snap_id: str) -> tuple[str, str]:
    raw = zpath.read_bytes()
    r = client.put(
        f'/v1/source-snapshots/{snap_id}',
        content=raw,
        headers={'Content-Type': 'application/zip', 'Content-Length': str(len(raw))},
    )
    assert r.status_code == 200, r.text
    g = client.get(f'/v1/source-snapshots/{snap_id}')
    assert g.status_code == 200 and g.json()['state'] == 'READY'
    return snap_id, r.json()['source_revision']


def _base_command():
    return {
        'name': 'default',
        'revision': 'cmd-rev-1',
        'template': {
            'single': ['python', '{tc_path}', '--com', '{com_a}'],
            'dual': ['python', '{tc_path}', '--a', '{com_a}', '--b', '{com_b}'],
        },
    }


def _wait_run_until(client: TestClient, run_id: str, states: set[str], timeout: float = 10.0) -> dict:
    deadline = time.monotonic() + timeout
    last = None
    while time.monotonic() < deadline:
        r = client.get(f'/v1/connector-runs/{run_id}')
        assert r.status_code == 200, r.text
        last = r.json()
        if last['state'] in states:
            return last
        time.sleep(0.05)
    raise AssertionError(f'Timed out waiting for {states}, last={last}')


def test_timeout_precedence_uses_600s_fallback():
    snap = {'default_seconds': 300, 'overrides': {'TC-OVR': 45}}
    assert resolve_step_timeout('TC-OVR', snap, 90) == 45
    assert resolve_step_timeout('TC-DEF', snap, 90) == 300
    assert resolve_step_timeout('TC-META', {}, 90) == 90
    assert resolve_step_timeout('TC-NONE', {}, None) == 600


def test_autonomous_multi_step_single_dual_chunked_installer_and_utf8_logs(tmp_path):
    _, runtime, host, app = _setup_host(tmp_path)
    try:
        zpath, src_snap_id, src_rev_expected = _build_source_zip(
            tmp_path,
            scripts={
                't1.py': "import sys; print('STEP1_한글로그_😀_OK'); print('Test Result: PASS'); sys.exit(0)\n",
                'dual/t2.py': "import sys; print('STEP2_DUAL_OK ' + ' '.join(sys.argv[1:])); print('Test Result: PASS'); sys.exit(0)\n",
            },
            metadata={'dual/t2.py': {'after': ['t1.py']}},
        )
        inst_zip, inst_id, inst_sha, inst_raw = _build_installer_zip(tmp_path)

        with TestClient(app, base_url='http://127.0.0.1:8772', client=('127.0.0.1', 5000)) as client:
            src_id, src_rev = _upload_source(client, zpath, src_snap_id)

            # Chunked sequential installer upload (2 chunks).
            mid = len(inst_raw) // 2
            c1 = client.put(
                f'/v1/installer-snapshots/{inst_id}',
                content=inst_raw[:mid],
                headers={
                    'Content-Type': 'application/zip',
                    'Content-Range': f'bytes 0-{mid - 1}/{len(inst_raw)}',
                    'Content-Length': str(mid),
                    'X-Archive-SHA256': inst_sha,
                },
            )
            assert c1.status_code == 200 and c1.json()['state'] == 'PARTIAL' and c1.json()['offset'] == mid
            c2 = client.put(
                f'/v1/installer-snapshots/{inst_id}',
                content=inst_raw[mid:],
                headers={
                    'Content-Type': 'application/zip',
                    'Content-Range': f'bytes {mid}-{len(inst_raw) - 1}/{len(inst_raw)}',
                    'Content-Length': str(len(inst_raw) - mid),
                    'X-Archive-SHA256': inst_sha,
                },
            )
            assert c2.status_code == 200 and c2.json()['state'] == 'READY'

            # Invalid dependency order rejected.
            bad_order = {
                'execution_mode': 'tc_only',
                'connection': {'a': {'host': 'WINPC', 'board_id': 'B1', 'com': 'COM3'}, 'b': {'host': 'WINPC', 'board_id': 'B2', 'com': 'COM4'}},
                'source_snapshot_id': src_id,
                'source_revision': src_rev,
                'command_snapshot': _base_command(),
                'tests': [
                    {'step_index': 0, 'tc_id': 'dual/t2.py', 'path': 'dual/t2.py', 'kind': 'Dual', 'after': ['t1.py']},
                    {'step_index': 1, 'tc_id': 't1.py', 'path': 't1.py', 'kind': 'Single'},
                ],
            }
            assert client.post('/v1/connector-runs', headers={'Idempotency-Key': 'bad-order'}, json=bad_order).status_code == 422

            req_payload = {
                'execution_mode': 'tc_only',
                'connection': {'a': {'host': 'WINPC', 'board_id': 'B1', 'com': 'COM3'}, 'b': {'host': 'WINPC', 'board_id': 'B2', 'com': 'COM4'}},
                'source_snapshot_id': src_id,
                'source_revision': src_rev,
                'command_snapshot': _base_command(),
                'tests': [
                    {'step_index': 0, 'tc_id': 't1.py', 'path': 't1.py', 'kind': 'Single'},
                    {'step_index': 1, 'tc_id': 'dual/t2.py', 'path': 'dual/t2.py', 'kind': 'Dual', 'after': ['t1.py']},
                ],
            }
            r1 = client.post('/v1/connector-runs', headers={'Idempotency-Key': 'run-1'}, json=req_payload)
            assert r1.status_code == 201
            run_id = r1.json()['run_id']
            # Same idempotency key + same body -> 200.
            r1_dup = client.post('/v1/connector-runs', headers={'Idempotency-Key': 'run-1'}, json=req_payload)
            assert r1_dup.status_code == 200 and r1_dup.json()['run_id'] == run_id

            done = _wait_run_until(client, run_id, {'COMPLETED'})
            assert done['outcome'] == 'PASSED'
            assert [s['state'] for s in done['steps']] == ['PASSED', 'PASSED']

            # UTF-8 boundary-safe small log chunk reading on step 0 attempt.
            att0 = done['attempts'][0]['attempt_id']
            chunks = []
            off = 0
            while True:
                lg = client.get(f'/v1/connector-runs/{run_id}/attempts/{att0}/logs?stream=stdout&offset={off}&limit=5').json()
                assert '\ufffd' not in lg['text']
                chunks.append(lg['text'])
                off = lg['next_offset']
                if lg['eof']:
                    break
            assert 'STEP1_한글로그_😀_OK' in ''.join(chunks)
    finally:
        host.close()


def test_pause_resume_and_safe_flashing_boundary_never_kills_flash(tmp_path, monkeypatch):
    _, runtime, host, app = _setup_host(tmp_path, with_flash=True)
    try:
        events = []

        class FakeConsole:
            def command(self, cmd): events.append(('cmd', cmd))
            def wait(self, pat, t): events.append(('wait', pat))
            def close(self): events.append(('close',))

        class FakeObserver:
            def __init__(self, *a, **kw):
                self.gaps = []
                self.writer_error = False
                self.evidence_overflow = False
                self.events = []
            def start(self): pass
            def boundary(self, kind, boot=False, expected_boot=False):
                if boot and expected_boot:
                    self.events.append({'kind': 'boot_signatures', 'expected': True, 'offset': len(self.events)})
                    self.events.append({'kind': 'login_markers', 'offset': len(self.events)})
                return 0
            def evidence(self, start=0):
                return {'events': self.events[start:], 'panic': False}
            def fence(self): return {'events': self.events, 'panic': False}
            def close(self): pass

        from backend.gui_test.execution import connector_runs
        monkeypatch.setattr(connector_runs, 'ConsoleObserver', FakeObserver)

        flash_started = __import__('threading').Event()
        allow_flash_finish = __import__('threading').Event()

        def fake_flash(profile, cfg, images, batch):
            flash_started.set()
            assert allow_flash_finish.wait(timeout=5.0)
            return {'terminated': True, 'exit_code': 0, 'stdout': 'FLASH_SUCCESS', 'stderr': ''}

        host.flashing.io = type('IO', (), {
            'console': staticmethod(lambda cfg: FakeConsole()),
            'devices': staticmethod(lambda p: ['SER-B1']),
            'flash': staticmethod(fake_flash),
        })()

        zpath, src_snap_id, _ = _build_source_zip(
            tmp_path,
            scripts={'t1.py': "import sys; print('Test Result: PASS'); sys.exit(0)\n"},
        )
        _, inst_id, inst_sha, inst_raw = _build_installer_zip(tmp_path)

        with TestClient(app, base_url='http://127.0.0.1:8772', client=('127.0.0.1', 5000)) as client:
            src_id, src_rev = _upload_source(client, zpath, src_snap_id)
            client.put(
                f'/v1/installer-snapshots/{inst_id}',
                content=inst_raw,
                headers={
                    'Content-Type': 'application/zip',
                    'Content-Range': f'bytes 0-{len(inst_raw) - 1}/{len(inst_raw)}',
                    'Content-Length': str(len(inst_raw)),
                    'X-Archive-SHA256': inst_sha,
                },
            )
            prof_rev = host.flash_profile_revisions['default']['revision']
            r = client.post(
                '/v1/connector-runs',
                headers={'Idempotency-Key': 'flash-safe-1'},
                json={
                    'execution_mode': 'flash_and_test',
                    'connection': {'a': {'host': 'WINPC', 'board_id': 'B1', 'com': 'COM3'}},
                    'source_snapshot_id': src_id,
                    'source_revision': src_rev,
                    'command_snapshot': _base_command(),
                    'installer': {'installer_snapshot_id': inst_id, 'flash_profile': 'default', 'flash_profile_revision': prof_rev},
                    'tests': [{'step_index': 0, 'tc_id': 't1.py', 'path': 't1.py', 'kind': 'Single'}],
                },
            )
            assert r.status_code == 201, r.text
            run_id = r.json()['run_id']
            assert flash_started.wait(timeout=5.0)
            # Request pause while BAT is actively running -> run enters PAUSE_REQUESTED, does NOT kill BAT.
            p = client.post(f'/v1/connector-runs/{run_id}/pause')
            assert p.status_code == 200 and p.json()['state'] == 'PAUSE_REQUESTED'
            allow_flash_finish.set()
            paused = _wait_run_until(client, run_id, {'PAUSED'})
            assert paused['pause_reason'] == 'OPERATOR_PAUSE'
            assert paused['steps'][0]['state'] == 'PENDING'
            # Resume continues into TC execution and finishes PASSED!
            res = client.post(f'/v1/connector-runs/{run_id}/resume')
            assert res.status_code == 200
            done = _wait_run_until(client, run_id, {'COMPLETED'})
            assert done['outcome'] == 'PASSED'
    finally:
        host.close()


def test_fail_stop_latch_claim_guard_retry_same_cause_stop_and_reprepare_child(tmp_path):
    _, runtime, host, app = _setup_host(tmp_path)
    try:
        flag_file = tmp_path / 'fail_flag.txt'
        flag_file.write_text('FAIL', encoding='utf-8')
        zpath, src1_snap_id, _ = _build_source_zip(
            tmp_path,
            scripts={
                't1.py': f"import sys; txt = open({repr(str(flag_file))}).read(); print('Test Result: ' + ('FAIL' if 'FAIL' in txt else 'PASS')); sys.exit(1 if 'FAIL' in txt else 0)\n",
                't2.py': "import sys; print('SHOULD_NOT_RUN'); sys.exit(0)\n",
            },
        )
        zpath_fixed, src2_snap_id, _ = _build_source_zip(
            tmp_path,
            name='src_fixed.zip',
            scripts={
                't1.py': "import sys; print('Test Result: PASS'); sys.exit(0)\n",
                't2.py': "import sys; print('Test Result: PASS'); sys.exit(0)\n",
            },
        )

        with TestClient(app, base_url='http://127.0.0.1:8772', client=('127.0.0.1', 5000)) as client:
            src1_id, src1_rev = _upload_source(client, zpath, src1_snap_id)
            src2_id, src2_rev = _upload_source(client, zpath_fixed, src2_snap_id)

            r = client.post(
                '/v1/connector-runs',
                headers={'Idempotency-Key': 'fail-stop-1'},
                json={
                    'execution_mode': 'tc_only',
                    'connection': {'a': {'host': 'WINPC', 'board_id': 'B1', 'com': 'COM3'}},
                    'source_snapshot_id': src1_id,
                    'source_revision': src1_rev,
                    'command_snapshot': _base_command(),
                    'tests': [
                        {'step_index': 0, 'tc_id': 't1.py', 'path': 't1.py', 'kind': 'Single'},
                        {'step_index': 1, 'tc_id': 't2.py', 'path': 't2.py', 'kind': 'Single'},
                    ],
                },
            )
            run_id = r.json()['run_id']
            latched = _wait_run_until(client, run_id, {'PAUSED'})
            assert latched['analysis_latched'] is True
            assert latched['pause_reason'] == 'FAILURE_STOP_LATCH'
            assert latched['steps'][1]['state'] == 'PENDING'

            # Manual resume MUST be rejected with 409 ANALYSIS_LATCH_ACTIVE!
            r_res = client.post(f'/v1/connector-runs/{run_id}/resume')
            assert r_res.status_code == 409 and r_res.json()['code'] == 'ANALYSIS_LATCH_ACTIVE'

            analyses = client.get('/v1/analyses?status=PENDING').json()['analyses']
            assert len(analyses) == 1
            aid = analyses[0]['analysis_id']

            claim = client.post(f'/v1/analyses/{aid}/claim', json={'lease_owner': 'plugin-1', 'lease_ttl_s': 60}).json()
            assert claim['status'] == 'ANALYZING' and claim['lease_token']

            # Unverified RETRY (verifier_status=FAILED) MUST force HOLD!
            blocked = client.post(
                f'/v1/analyses/{aid}/decision',
                json={
                    'lease_token': claim['lease_token'],
                    'expected_evidence_revision': latched['version'],
                    'verdict': 'RETRY',
                    'cause_key': 'transient:boot',
                    'summary': 'try anyway',
                    'verifier_status': 'FAILED',
                },
            ).json()
            assert blocked['analysis']['status'] == 'HOLD'
            assert blocked['analysis']['decision']['hold_reason'] == 'VERIFIER_GATE_BLOCKED'

            # Re-open another run to test RETRY -> same cause stop -> REPREPARE child!
            client.post(f'/v1/analyses/{aid}/acknowledge-hold', json={'operator': 'tester', 'note': 'ack'})

            r2 = client.post(
                '/v1/connector-runs',
                headers={'Idempotency-Key': 'fail-stop-2'},
                json={
                    'execution_mode': 'tc_only',
                    'connection': {'a': {'host': 'WINPC', 'board_id': 'B1', 'com': 'COM3'}},
                    'source_snapshot_id': src1_id,
                    'source_revision': src1_rev,
                    'command_snapshot': _base_command(),
                    'tests': [
                        {'step_index': 0, 'tc_id': 't1.py', 'path': 't1.py', 'kind': 'Single'},
                        {'step_index': 1, 'tc_id': 't2.py', 'path': 't2.py', 'kind': 'Single'},
                    ],
                },
            ).json()
            run2 = _wait_run_until(client, r2['run_id'], {'PAUSED'})
            aid2 = client.get(f'/v1/analyses?status=PENDING&run_id={run2["run_id"]}').json()['analyses'][0]['analysis_id']
            claim2 = client.post(f'/v1/analyses/{aid2}/claim', json={'lease_owner': 'plugin-1'}).json()

            # REPREPARE with src2 -> closes run2 immutably as SUPERSEDED_BY_REPREPARE and executes child run to PASSED!
            rep = client.post(
                f'/v1/analyses/{aid2}/decision',
                json={
                    'lease_token': claim2['lease_token'],
                    'expected_evidence_revision': run2['version'],
                    'verdict': 'REPREPARE',
                    'cause_key': 'bad:script_bug',
                    'summary': 'fixed script',
                    'verifier_status': 'PASSED',
                    'reprepare': {'source_snapshot_id': src2_id, 'source_revision': src2_rev},
                },
            ).json()
            assert rep['run']['outcome'] == 'SUPERSEDED_BY_REPREPARE'
            assert rep['run']['source_snapshot_id'] == src1_id
            child_id = rep['child_run']['run_id']
            assert rep['child_run']['parent_run_id'] == run2['run_id']
            child_done = _wait_run_until(client, child_id, {'COMPLETED'})
            assert child_done['outcome'] == 'PASSED'
            # REPREPARE hashes the generated child request in the parent transaction.
            with host.connector._connect() as db:
                row = db.execute('SELECT request_json, body_fingerprint FROM connector_runs WHERE run_id=?', (child_id,)).fetchone()
            child_input = json.loads(row['request_json'])
            child_input.pop('request_hash')
            assert row['body_fingerprint'] == digest(child_input)
            headers = {'Idempotency-Key': child_done['idempotency_key']}
            replay = client.post('/v1/connector-runs', json=child_input, headers=headers)
            assert replay.status_code == 200 and replay.json()['outcome'] == 'PASSED'
            changed = client.post('/v1/connector-runs', json=child_input | {'run_id': None}, headers=headers)
            assert changed.status_code == 409 and changed.json()['code'] == 'IDEMPOTENCY_CONFLICT'
    finally:
        host.close()


def test_crash_recovery_unknown_retention_and_delete_tombstone(tmp_path):
    _, runtime, host, app = _setup_host(tmp_path)
    try:
        zpath, src_snap_id, _ = _build_source_zip(
            tmp_path,
            scripts={'t1.py': "import sys; print('Test Result: PASS'); sys.exit(0)\n"},
        )
        with TestClient(app, base_url='http://127.0.0.1:8772', client=('127.0.0.1', 5000)) as client:
            src_id, src_rev = _upload_source(client, zpath, src_snap_id)
            run = client.post(
                '/v1/connector-runs',
                headers={'Idempotency-Key': 'rec-1'},
                json={
                    'execution_mode': 'tc_only',
                    'connection': {'a': {'host': 'WINPC', 'board_id': 'B1', 'com': 'COM3'}},
                    'source_snapshot_id': src_id,
                    'source_revision': src_rev,
                    'command_snapshot': _base_command(),
                    'tests': [{'step_index': 0, 'tc_id': 't1.py', 'path': 't1.py', 'kind': 'Single'}],
                },
            ).json()
            run_id = run['run_id']
            done = _wait_run_until(client, run_id, {'COMPLETED'})
            assert done['outcome'] == 'PASSED'

        # Simulate unexpected crash mid-RUNNING in DB -> restart Host -> recover() marks UNKNOWN!
        import sqlite3
        with sqlite3.connect(host.db) as c:
            c.execute("UPDATE connector_runs SET state='RUNNING', outcome=NULL, ended_at=NULL WHERE run_id=?", (run_id,))
            c.commit()
        host.recover()

        with TestClient(app, base_url='http://127.0.0.1:8772', client=('127.0.0.1', 5000)) as client:
            cur = client.get(f'/v1/connector-runs/{run_id}').json()
            assert cur['state'] == 'UNKNOWN'
            assert cur['recovery_reason'] == 'HOST_RESTARTED_DURING_EXECUTION'

            # Retention MUST protect UNKNOWN run's source snapshot even at future clock!
            rep_dry = retention.collect(host, dry_run=True, clock=time.time() + 10**9)
            assert not any(src_id in str(p) for p in rep_dry.get('deleted', []))

            # New run blocked until reconciled.
            blocked = client.post(
                '/v1/connector-runs',
                headers={'Idempotency-Key': 'rec-2'},
                json={
                    'execution_mode': 'tc_only',
                    'connection': {'a': {'host': 'WINPC', 'board_id': 'B1', 'com': 'COM3'}},
                    'source_snapshot_id': src_id,
                    'source_revision': src_rev,
                    'command_snapshot': _base_command(),
                    'tests': [{'step_index': 0, 'tc_id': 't1.py', 'path': 't1.py', 'kind': 'Single'}],
                },
            )
            assert blocked.status_code == 409 and blocked.json()['code'] == 'ACTIVE_RUN_EXISTS'

            # Delete blocked while UNKNOWN -> reconcile MARK_ABORTED -> delete creates 410 tombstone!
            assert client.delete(f'/v1/connector-runs/{run_id}').status_code == 409
            rec = client.post(f'/v1/connector-runs/{run_id}/reconcile', json={'action': 'MARK_ABORTED', 'reason': 'power lost'}).json()
            assert rec['state'] == 'COMPLETED' and rec['outcome'] == 'ABORTED'
            assert client.delete(f'/v1/connector-runs/{run_id}').status_code == 200
            assert client.get(f'/v1/connector-runs/{run_id}').status_code == 410
    finally:
        host.close()


def test_update_settings_invalid_boards_does_not_corrupt_in_memory_config(tmp_path):
    _, _, host, app = _setup_host(tmp_path)
    try:
        orig_boards = list(host.configured_boards)
        orig_cfg_boards = list(host.connector.config['boards'])
        with TestClient(app, base_url='http://127.0.0.1:8772', client=('127.0.0.1', 5000)) as client:
            s0 = client.get('/v1/control/settings').json()
            bad = client.put('/v1/control/settings', json={
                'expected_revision': s0['revision'],
                'source': 'linux',
                'patch': {'boards': [{'bad_key': 1}]},
            })
            assert bad.status_code == 422
            assert host.configured_boards == orig_boards
            assert host.connector.config['boards'] == orig_cfg_boards
    finally:
        host.close()


def test_console_hub_respects_connector_run_observers_and_session_deletion_blocks_on_connector_run(tmp_path):
    import sqlite3
    from backend.gui_test.connector.console import ConsoleHub
    from backend.gui_test.core.models import TestError
    from backend.gui_test.execution.session_deletion import delete_session

    _, _, host, _ = _setup_host(tmp_path)
    try:
        rx_cfg = {'port': 'COM19', 'rx_only_confirmed': True, 'control_lines_isolated': True}

        class FakeNormalObserver:
            created = []

            def __init__(self, directory, config):
                self.directory = directory
                self.config = config
                self.closed = False
                self.tail = 'NORMAL_RX_TAIL'
                FakeNormalObserver.created.append(self)

            def start(self):
                pass

            def close(self):
                self.closed = True

            def evidence(self):
                return {'phase': 'IDLE', 'complete': True, 'panic': False, 'end_offset': 10, 'tail': self.tail, 'events': [], 'gaps': []}

        hub = ConsoleHub(host, {'B1': rx_cfg}, factory=FakeNormalObserver)
        hub.refresh()
        assert 'B1' in hub.normal
        normal_first = hub.normal['B1']
        assert not normal_first.closed

        run_id = 'c' * 32
        with sqlite3.connect(host.db) as c:
            c.execute(
                'INSERT INTO connector_runs(run_id, idempotency_key, request_hash, execution_mode, state, '
                'analysis_latched, pause_requested, cancel_requested, current_step_index, version, '
                'source_snapshot_id, request_json, retry_chain_json, created_at, updated_at) '
                'VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                (
                    run_id,
                    'k-obs',
                    'a' * 64,
                    'flash_and_test',
                    'FLASHING',
                    0,
                    0,
                    0,
                    0,
                    1,
                    'b' * 64,
                    json.dumps({'connection': {'a': {'host': 'WINPC', 'board_id': 'B1', 'com': 'COM3'}}}),
                    '{}',
                    time.time(),
                    time.time(),
                ),
            )
            c.execute(
                'INSERT INTO jobs VALUES(?,?,?)',
                ('d' * 32, 'h', json.dumps({'id': 'd' * 32, 'state': 'DONE', 'terminated': True})),
            )
            c.commit()

        class FakeRunObserver:
            def __init__(self):
                self.board_id = 'B1'
                self.config = rx_cfg

            def evidence(self):
                return {'phase': 'FLASHING', 'complete': True, 'panic': False, 'end_offset': 42, 'tail': 'FLASH_OBS_TAIL', 'events': [], 'gaps': []}

        host.connector._run_observers[run_id] = [FakeRunObserver()]

        # ConsoleHub.refresh() must suspend normal['B1'], NOT recreate normal['B1'], and project FakeRunObserver + run_id!
        hub.refresh()
        assert normal_first.closed is True
        assert 'B1' not in hub.normal
        assert len(FakeNormalObserver.created) == 1
        proj = hub.projection()
        b1_row = next(r for r in proj['boards'] if r['board_id'] == 'B1')
        assert b1_row['source'] == 'batch-observer'
        assert b1_row['text'] == 'FLASH_OBS_TAIL'
        assert run_id in b1_row['run_ids']

        # delete_session MUST reject deletion while connector_run is active (SESSION_ACTIVE).
        with pytest.raises(TestError) as exc_info:
            delete_session(host, {'runner_id': host.identity, 'execution_ids': ['d' * 32]})
        assert exc_info.value.code == 'SESSION_ACTIVE'

        # Once connector_run finishes and observers close, delete_session succeeds and ConsoleHub resumes normal['B1'].
        host.connector._run_observers.pop(run_id, None)
        with sqlite3.connect(host.db) as c:
            c.execute("UPDATE connector_runs SET state='COMPLETED', outcome='PASSED' WHERE run_id=?", (run_id,))
            c.commit()
        del_res = delete_session(host, {'runner_id': host.identity, 'execution_ids': ['d' * 32]})
        assert del_res['deleted'] is True
        hub.refresh()
        assert 'B1' in hub.normal
        hub.close()
    finally:
        host.close()


def test_flash_and_test_under_proxy_transport_and_non_jobs_item_save(tmp_path, monkeypatch):
    import queue
    import threading
    from backend.gui_test.execution import flashing as flashing_module

    class FakeProxyPort:
        def __init__(self):
            self.input = queue.Queue()
            self.written = []
            self.opened = True
            self.cts = self.dsr = True
            self.cd = self.ri = False
            self.out_waiting = 0
            self.dtr = self.rts = False
            self.baudrate = 115200
            self.fastboot_ready = False

        def read(self, size):
            if not self.opened:
                raise OSError('closed')
            try:
                return self.input.get(timeout=0.01)
            except queue.Empty:
                return b''

        @property
        def in_waiting(self):
            with self.input.mutex:
                return sum(len(d) for d in self.input.queue)

        def write(self, data):
            self.written.append(data)
            if b'reboot lkshell' in data:
                self.input.put(b'lkshell>\n')
            elif b'fast' in data:
                self.fastboot_ready = True
            return len(data)

        def flush(self):
            pass

        def reset_output_buffer(self):
            pass

        def close(self):
            self.opened = False

    home = tmp_path / 'winhome'
    runtime = home / 'runtime'
    runtime.mkdir(parents=True, exist_ok=True)
    flash_cfg = _make_flash_config(tmp_path)
    flash_cfg['profiles']['default']['boards']['B1']['observer']['boot_signatures'] = ['Booting Linux']
    cfg = {
        'python': sys.executable,
        'boards': [
            {'host': 'WINPC', 'board_id': 'B1', 'com': 'COM3'},
        ],
        'serial_transport': 'proxy',
        'flashing': flash_cfg,
    }
    cfg_path = home / 'windows-runner.json'
    cfg_path.write_text(json.dumps(cfg), encoding='utf-8')
    host = Host(cfg, runtime, ports=lambda: {'COM3'}, config_path=cfg_path)
    port = FakeProxyPort()
    host.multiplexers.ports['B1'].factory = lambda *_: port
    host.recover()
    try:
        observed_items = []

        def fake_devices(profile):
            return ['SER-B1'] if port.fastboot_ready else []

        def fake_flash(profile, bcfg, images, batch):
            observed_items.append(dict(host.flashing.context.item))
            port.input.put(b'Booting Linux\nlogin:\n')
            return {'terminated': True, 'exit_code': 0, 'stdout': 'FLASH_SUCCESS', 'stderr': ''}

        # Keep real proxy_console as host.flashing.io.console!
        host.flashing.io = type('IO', (), {
            'console': host.flashing.console,
            'devices': staticmethod(fake_devices),
            'flash': staticmethod(fake_flash),
        })()

        zpath, src_snap_id, _ = _build_source_zip(
            tmp_path,
            scripts={'t1.py': "import sys; print('Test Result: PASS'); sys.exit(0)\n"},
        )
        _, inst_id, inst_sha, inst_raw = _build_installer_zip(tmp_path)

        with TestClient(create_app(host), base_url='http://127.0.0.1:8772', client=('127.0.0.1', 5000)) as client:
            src_id, src_rev = _upload_source(client, zpath, src_snap_id)
            client.put(
                f'/v1/installer-snapshots/{inst_id}',
                content=inst_raw,
                headers={
                    'Content-Type': 'application/zip',
                    'Content-Range': f'bytes 0-{len(inst_raw) - 1}/{len(inst_raw)}',
                    'Content-Length': str(len(inst_raw)),
                    'X-Archive-SHA256': inst_sha,
                },
            )
            prof_rev = host.flash_profile_revisions['default']['revision']
            r = client.post(
                '/v1/connector-runs',
                headers={'Idempotency-Key': 'proxy-flash-1'},
                json={
                    'execution_mode': 'flash_and_test',
                    'connection': {'a': {'host': 'WINPC', 'board_id': 'B1', 'com': 'COM3'}},
                    'source_snapshot_id': src_id,
                    'source_revision': src_rev,
                    'command_snapshot': _base_command(),
                    'installer': {'installer_snapshot_id': inst_id, 'flash_profile': 'default', 'flash_profile_revision': prof_rev},
                    'tests': [{'step_index': 0, 'tc_id': 't1.py', 'path': 't1.py', 'kind': 'Single'}],
                },
            )
            assert r.status_code == 201, r.text
            run_id = r.json()['run_id']
            done = _wait_run_until(client, run_id, {'COMPLETED'})
            assert done['outcome'] == 'PASSED', done
            assert observed_items and observed_items[0]['id'] == done['attempts'][0]['attempt_id']
            assert getattr(host.flashing.context, 'item', None) is None
            assert b'reboot lkshell\r' in port.written
            assert b'fast\r' in port.written
            assert host.multiplexers.ports['B1'].owner is None

        # Verify FlashService.run/supervise tolerate a non-jobs dict context.item when host.save rejects unknown IDs.
        save_calls = []
        host.jobs = {}
        monkeypatch.setattr(host, 'save', lambda item: save_calls.append(item))

        class FakeTree:
            def __init__(self, *a, **kw):
                self.process = type('P', (), {'pid': 4242, 'stdout': None, 'stderr': None, 'poll': staticmethod(lambda: 0)})()
                self._stopped = False

            def stopped(self):
                return self._stopped

            def stop(self):
                self._stopped = True
                return True

            def close(self):
                pass

        class FakeCap:
            def __init__(self, *a, **kw):
                pass

            def drain(self):
                return True

            def snapshot(self):
                return {'stdout': 'ok', 'stderr': ''}, False

        monkeypatch.setattr(flashing_module, 'ProcessTree', FakeTree)
        monkeypatch.setattr(flashing_module, 'Capture', FakeCap)

        non_job_item = {'id': 'f' * 32, 'request': {'connection': {'a': {'host': 'WINPC', 'board_id': 'B1', 'com': 'COM3'}}}}
        host.flashing.context.item = non_job_item
        try:
            # Force timeout -> supervise() runs and retains tree until _stopped flips.
            with pytest.raises(flashing_module.UnknownHardware):
                host.flashing.run(['fake'], runtime, 0, flashing=True)
            assert non_job_item['process_receipt']['state'] == 'UNKNOWN'
            for tree, _ in list(host.flashing.supervised.values()):
                tree._stopped = True
            deadline = time.monotonic() + 3.0
            while host.flashing.supervised and time.monotonic() < deadline:
                time.sleep(0.02)
            assert not host.flashing.supervised
            assert non_job_item['process_receipt']['state'] == 'EXITED'
            assert save_calls == []
        finally:
            host.flashing.context.item = None
    finally:
        host.close()


def test_flash_timeout_marks_unknown_and_supervised_blocks_retry(tmp_path, monkeypatch):
    import threading
    from backend.gui_test.execution import connector_runs
    from backend.gui_test.execution.flashing import UnknownHardware

    _, _, host, app = _setup_host(tmp_path, with_flash=True)
    try:
        class FakeConsole:
            def command(self, cmd): pass
            def wait(self, pat, t): pass
            def close(self): pass

        class FakeObserver:
            def __init__(self, *a, **kw):
                self.gaps = []
                self.writer_error = False
                self.evidence_overflow = False
                self.events = []
            def start(self): pass
            def boundary(self, kind, boot=False, expected_boot=False): return 0
            def evidence(self, start=0): return {'events': self.events[start:], 'panic': False}
            def fence(self): return {'events': self.events, 'panic': False}
            def close(self): pass

        monkeypatch.setattr(connector_runs, 'ConsoleObserver', FakeObserver)
        natural_exit = threading.Event()
        mode = {'kind': 'timeout'}

        class SupervisedTree:
            def __init__(self):
                self.process = type('P', (), {'pid': 9876, 'poll': staticmethod(lambda: 0)})()
                self.closed = False

            def stopped(self):
                return natural_exit.is_set()

            def close(self):
                self.closed = True

        class SupervisedCap:
            def drain(self):
                return True

        def fake_flash(profile, cfg, images, batch):
            if mode['kind'] == 'timeout':
                host.flashing.supervise(SupervisedTree(), SupervisedCap(), {'argv': ['flash.bat'], 'started_at': time.time()})
                raise UnknownHardware('Flash supervision limit reached', 'HARDWARE_UNKNOWN')
            raise UnknownHardware('Console panic during flash', 'CONSOLE_UNSAFE')

        host.flashing.io = type('IO', (), {
            'console': staticmethod(lambda cfg: FakeConsole()),
            'devices': staticmethod(lambda p: ['SER-B1']),
            'flash': staticmethod(fake_flash),
        })()

        zpath, src_snap_id, _ = _build_source_zip(
            tmp_path,
            scripts={'t1.py': "import sys; print('Test Result: PASS'); sys.exit(0)\n"},
        )
        _, inst_id, inst_sha, inst_raw = _build_installer_zip(tmp_path)

        with TestClient(app, base_url='http://127.0.0.1:8772', client=('127.0.0.1', 5000)) as client:
            src_id, src_rev = _upload_source(client, zpath, src_snap_id)
            client.put(
                f'/v1/installer-snapshots/{inst_id}',
                content=inst_raw,
                headers={
                    'Content-Type': 'application/zip',
                    'Content-Range': f'bytes 0-{len(inst_raw) - 1}/{len(inst_raw)}',
                    'Content-Length': str(len(inst_raw)),
                    'X-Archive-SHA256': inst_sha,
                },
            )
            prof_rev = host.flash_profile_revisions['default']['revision']
            r = client.post(
                '/v1/connector-runs',
                headers={'Idempotency-Key': 'flash-timeout-1'},
                json={
                    'execution_mode': 'flash_and_test',
                    'connection': {'a': {'host': 'WINPC', 'board_id': 'B1', 'com': 'COM3'}},
                    'source_snapshot_id': src_id,
                    'source_revision': src_rev,
                    'command_snapshot': _base_command(),
                    'installer': {'installer_snapshot_id': inst_id, 'flash_profile': 'default', 'flash_profile_revision': prof_rev},
                    'tests': [{'step_index': 0, 'tc_id': 't1.py', 'path': 't1.py', 'kind': 'Single'}],
                },
            )
            assert r.status_code == 201
            run_id = r.json()['run_id']
            unk = _wait_run_until(client, run_id, {'UNKNOWN'})
            assert unk['recovery_reason'] == 'HARDWARE_UNKNOWN'
            assert unk['analysis_latched'] is False
            assert unk['attempts'][0]['state'] == 'UNKNOWN'
            assert bool(host.flashing.supervised)

            # Reconcile UNKNOWN -> MARK_FAILED_FOR_ANALYSIS -> attempt RETRY while supervised is still active -> HOLD (PROCESS_NOT_STOPPED).
            rec = client.post(f'/v1/connector-runs/{run_id}/reconcile', json={'action': 'MARK_FAILED_FOR_ANALYSIS', 'reason': 'inspect'})
            assert rec.status_code == 200 and rec.json()['state'] == 'PAUSED'
            aid = client.get(f'/v1/analyses?status=PENDING&run_id={run_id}').json()['analyses'][0]['analysis_id']
            claim = client.post(f'/v1/analyses/{aid}/claim', json={'lease_owner': 'plugin-1'}).json()
            dec = client.post(
                f'/v1/analyses/{aid}/decision',
                json={
                    'lease_token': claim['lease_token'],
                    'expected_evidence_revision': rec.json()['version'],
                    'verdict': 'RETRY',
                    'cause_key': 'flash:timeout',
                    'summary': 'retry',
                    'verifier_status': 'PASSED',
                },
            ).json()
            assert dec['analysis']['status'] == 'HOLD'
            assert dec['analysis']['decision']['hold_reason'] == 'PROCESS_NOT_STOPPED'

            natural_exit.set()
            deadline = time.monotonic() + 3.0
            while host.flashing.supervised and time.monotonic() < deadline:
                time.sleep(0.02)
            assert host.connector._processes_stopped_for_run(run_id) is True

            # Clean up first run so second run can start, and verify CONSOLE_UNSAFE without supervised still latches PAUSED.
            client.post(f'/v1/analyses/{aid}/acknowledge-hold', json={'operator': 'op', 'note': 'done'})
            mode['kind'] = 'console_unsafe'
            r2 = client.post(
                '/v1/connector-runs',
                headers={'Idempotency-Key': 'flash-unsafe-1'},
                json={
                    'execution_mode': 'flash_and_test',
                    'connection': {'a': {'host': 'WINPC', 'board_id': 'B1', 'com': 'COM3'}},
                    'source_snapshot_id': src_id,
                    'source_revision': src_rev,
                    'command_snapshot': _base_command(),
                    'installer': {'installer_snapshot_id': inst_id, 'flash_profile': 'default', 'flash_profile_revision': prof_rev},
                    'tests': [{'step_index': 0, 'tc_id': 't1.py', 'path': 't1.py', 'kind': 'Single'}],
                },
            )
            assert r2.status_code == 201
            latched = _wait_run_until(client, r2.json()['run_id'], {'PAUSED'})
            assert latched['analysis_latched'] is True
            assert latched['pause_reason'] == 'FAILURE_STOP_LATCH'
    finally:
        host.close()


def test_paused_run_is_active_and_blocks_concurrent_runs_and_host_stop(tmp_path):
    from backend.gui_test.core.models import TestError, uid

    _, _, host, app = _setup_host(tmp_path, with_flash=True)
    try:
        gate_file = tmp_path / 'step1_gate.txt'
        zpath, src_snap_id, _ = _build_source_zip(
            tmp_path,
            scripts={
                't1.py': (
                    f"import pathlib, time; p = pathlib.Path({repr(str(gate_file))}); "
                    "p.with_name('step1_started.txt').write_text('1'); "
                    "deadline = time.monotonic() + 5.0\n"
                    "while not p.exists() and time.monotonic() < deadline: time.sleep(0.02)\n"
                    "print('Test Result: PASS')\n"
                ),
                't2.py': "print('Test Result: PASS')\n",
            },
        )
        with TestClient(app, base_url='http://127.0.0.1:8772', client=('127.0.0.1', 5000)) as client:
            src_id, src_rev = _upload_source(client, zpath, src_snap_id)
            r = client.post(
                '/v1/connector-runs',
                headers={'Idempotency-Key': 'pause-block-1'},
                json={
                    'execution_mode': 'tc_only',
                    'connection': {'a': {'host': 'WINPC', 'board_id': 'B1', 'com': 'COM3'}},
                    'source_snapshot_id': src_id,
                    'source_revision': src_rev,
                    'command_snapshot': _base_command(),
                    'tests': [
                        {'step_index': 0, 'tc_id': 't1.py', 'path': 't1.py', 'kind': 'Single'},
                        {'step_index': 1, 'tc_id': 't2.py', 'path': 't2.py', 'kind': 'Single'},
                    ],
                },
            )
            assert r.status_code == 201
            run_id = r.json()['run_id']
            started_marker = gate_file.with_name('step1_started.txt')
            deadline = time.monotonic() + 5.0
            while not started_marker.exists() and time.monotonic() < deadline:
                time.sleep(0.02)
            assert started_marker.exists()

            p = client.post(f'/v1/connector-runs/{run_id}/pause')
            assert p.status_code == 200 and p.json()['state'] == 'PAUSE_REQUESTED'
            gate_file.write_text('go', encoding='utf-8')
            paused = _wait_run_until(client, run_id, {'PAUSED'})
            assert paused['pause_reason'] == 'OPERATOR_PAUSE'
            assert paused['analysis_latched'] is False

            active = client.get('/v1/connector-runs/active').json()
            assert active['active'] is True and active['run']['run_id'] == run_id and active['run']['state'] == 'PAUSED'
            assert host.connector.has_blocking_run() is True
            assert host.safe_to_stop() is False
            assert host.connector.has_active_execution_for_restart() is False

            r2 = client.post(
                '/v1/connector-runs',
                headers={'Idempotency-Key': 'pause-block-2'},
                json={
                    'execution_mode': 'tc_only',
                    'connection': {'a': {'host': 'WINPC', 'board_id': 'B1', 'com': 'COM3'}},
                    'source_snapshot_id': src_id,
                    'source_revision': src_rev,
                    'command_snapshot': _base_command(),
                    'tests': [{'step_index': 0, 'tc_id': 't2.py', 'path': 't2.py', 'kind': 'Single'}],
                },
            )
            assert r2.status_code == 409 and r2.json()['code'] == 'ACTIVE_RUN_EXISTS'

            with pytest.raises(TestError) as exc_info:
                host.start({
                    'id': uid(),
                    'tc_id': 't2.py',
                    'source_revision': src_rev,
                    'snapshot_id': src_id,
                    'connection': {'a': {'host': 'WINPC', 'board_id': 'B1', 'com': 'COM3'}},
                    'template': _base_command()['template'],
                })
            assert exc_info.value.code == 'CONNECTOR_BUSY'

            assert client.post(f'/v1/connector-runs/{run_id}/resume').status_code == 200
            done = _wait_run_until(client, run_id, {'COMPLETED'})
            assert done['outcome'] == 'PASSED'
            assert client.get('/v1/connector-runs/active').json()['active'] is False
            assert host.connector.has_blocking_run() is False
            assert host.safe_to_stop() is True
    finally:
        host.close()


def test_unannotated_discovered_tc_defaults_to_600s_timeout(tmp_path):
    from backend.gui_test.core.discovery import discover

    _, _, host, app = _setup_host(tmp_path)
    try:
        src_tree = tmp_path / 'discovered_src'
        src_tree.mkdir()
        (src_tree / 'plain.py').write_text("print('Test Result: PASS')\n", encoding='utf-8')
        discovered = discover(src_tree)
        assert discovered['tests'][0]['timeout'] == 120
        assert discovered['tests'][0]['timeout_explicit'] is False

        zpath, snap_id, _ = _build_source_zip(
            tmp_path,
            name='disc.zip',
            scripts={'plain.py': "print('Test Result: PASS')\n"},
        )

        with TestClient(app, base_url='http://127.0.0.1:8772', client=('127.0.0.1', 5000)) as client:
            src_id, src_rev = _upload_source(client, zpath, snap_id)
            r = client.post(
                '/v1/connector-runs',
                headers={'Idempotency-Key': 'disc-timeout-1'},
                json={
                    'execution_mode': 'tc_only',
                    'connection': {'a': {'host': 'WINPC', 'board_id': 'B1', 'com': 'COM3'}},
                    'source_snapshot_id': src_id,
                    'source_revision': src_rev,
                    'command_snapshot': _base_command(),
                    'timeout_settings_snapshot': {},
                    'tests': [{'step_index': 0, 'tc_id': 'plain.py', 'path': 'plain.py', 'kind': 'Single'}],
                },
            )
            assert r.status_code == 201, r.text
            assert r.json()['steps'][0]['effective_timeout_s'] == 600
            done = _wait_run_until(client, r.json()['run_id'], {'COMPLETED'})
            assert done['outcome'] == 'PASSED'
    finally:
        host.close()


def test_resume_pause_requested_during_flashing_and_guarded_start_transitions(tmp_path, monkeypatch):
    import sqlite3
    import threading
    from backend.gui_test.execution import connector_runs

    _, runtime, host, app = _setup_host(tmp_path, with_flash=True)
    try:
        class FakeConsole:
            def command(self, cmd): pass
            def wait(self, pat, t): pass
            def close(self): pass

        class FakeObserver:
            def __init__(self, *a, **kw):
                self.gaps = []
                self.writer_error = False
                self.evidence_overflow = False
                self.events = []
            def start(self): pass
            def boundary(self, kind, boot=False, expected_boot=False):
                if boot and expected_boot:
                    self.events.append({'kind': 'boot_signatures', 'expected': True, 'offset': len(self.events)})
                    self.events.append({'kind': 'login_markers', 'offset': len(self.events)})
                return 0
            def evidence(self, start=0): return {'events': self.events[start:], 'panic': False}
            def fence(self): return {'events': self.events, 'panic': False}
            def close(self): pass

        monkeypatch.setattr(connector_runs, 'ConsoleObserver', FakeObserver)
        flash_started = threading.Event()
        allow_flash_finish = threading.Event()

        def fake_flash(profile, cfg, images, batch):
            flash_started.set()
            assert allow_flash_finish.wait(timeout=5.0)
            return {'terminated': True, 'exit_code': 0, 'stdout': 'FLASH_SUCCESS', 'stderr': ''}

        host.flashing.io = type('IO', (), {
            'console': staticmethod(lambda cfg: FakeConsole()),
            'devices': staticmethod(lambda p: ['SER-B1']),
            'flash': staticmethod(fake_flash),
        })()

        zpath, src_snap_id, _ = _build_source_zip(
            tmp_path,
            scripts={'t1.py': "import sys; print('Test Result: PASS'); sys.exit(0)\n"},
        )
        _, inst_id, inst_sha, inst_raw = _build_installer_zip(tmp_path)

        with TestClient(app, base_url='http://127.0.0.1:8772', client=('127.0.0.1', 5000)) as client:
            src_id, src_rev = _upload_source(client, zpath, src_snap_id)
            client.put(
                f'/v1/installer-snapshots/{inst_id}',
                content=inst_raw,
                headers={
                    'Content-Type': 'application/zip',
                    'Content-Range': f'bytes 0-{len(inst_raw) - 1}/{len(inst_raw)}',
                    'Content-Length': str(len(inst_raw)),
                    'X-Archive-SHA256': inst_sha,
                },
            )
            prof_rev = host.flash_profile_revisions['default']['revision']
            r = client.post(
                '/v1/connector-runs',
                headers={'Idempotency-Key': 'flash-resume-clear-1'},
                json={
                    'execution_mode': 'flash_and_test',
                    'connection': {'a': {'host': 'WINPC', 'board_id': 'B1', 'com': 'COM3'}},
                    'source_snapshot_id': src_id,
                    'source_revision': src_rev,
                    'command_snapshot': _base_command(),
                    'installer': {'installer_snapshot_id': inst_id, 'flash_profile': 'default', 'flash_profile_revision': prof_rev},
                    'tests': [{'step_index': 0, 'tc_id': 't1.py', 'path': 't1.py', 'kind': 'Single'}],
                },
            )
            assert r.status_code == 201
            run_id = r.json()['run_id']
            assert flash_started.wait(timeout=5.0)
            p = client.post(f'/v1/connector-runs/{run_id}/pause')
            assert p.status_code == 200 and p.json()['state'] == 'PAUSE_REQUESTED'
            res = client.post(f'/v1/connector-runs/{run_id}/resume')
            assert res.status_code == 200 and res.json()['state'] == 'FLASHING'
            allow_flash_finish.set()
            done = _wait_run_until(client, run_id, {'COMPLETED'})
            assert done['outcome'] == 'PASSED'

            # Guarded transition: a cancelled QUEUED run must not be resurrected by _execute_flashing_phase or _execute_run.
            host.connector.close()
            r2 = client.post(
                '/v1/connector-runs',
                headers={'Idempotency-Key': 'cancel-guard-1'},
                json={
                    'execution_mode': 'tc_only',
                    'connection': {'a': {'host': 'WINPC', 'board_id': 'B1', 'com': 'COM3'}},
                    'source_snapshot_id': src_id,
                    'source_revision': src_rev,
                    'command_snapshot': _base_command(),
                    'tests': [{'step_index': 0, 'tc_id': 't1.py', 'path': 't1.py', 'kind': 'Single'}],
                },
            )
            assert r2.status_code == 201
            run2_id = r2.json()['run_id']
            c_res = client.post(f'/v1/connector-runs/{run2_id}/cancel')
            assert c_res.status_code == 200 and c_res.json()['state'] == 'COMPLETED' and c_res.json()['outcome'] == 'CANCELLED'
            run2_dir = runtime / 'connector-snapshots' / run2_id
            assert host.connector._execute_flashing_phase(run2_id, {'connection': {'a': {'host': 'WINPC', 'board_id': 'B1', 'com': 'COM3'}}}, run2_dir, 1) == 'CANCELLED'
            host.connector._execute_run(run2_id)
            after = client.get(f'/v1/connector-runs/{run2_id}').json()
            assert after['state'] == 'COMPLETED' and after['outcome'] == 'CANCELLED' and after['attempts'] == []

            # Atomic settings + settings_sync_state update.
            s0 = client.get('/v1/control/settings').json()
            r_s1 = client.put('/v1/control/settings', json={
                'expected_revision': s0['revision'],
                'source': 'windows',
                'patch': {'timeouts': {'default_seconds': 450, 'overrides': {}}},
            })
            assert r_s1.status_code == 200, r_s1.text
            s1 = r_s1.json()
            with sqlite3.connect(host.db) as db:
                row = db.execute('SELECT data_json FROM settings_sync_state WHERE id=1').fetchone()
                sync = json.loads(row[0])
            assert sync['dirty_on_windows'] is True
            assert sync['windows_revision'] == s1['revision']
    finally:
        host.close()

