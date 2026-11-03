"""Server ownership and host result checks for the optional flash/TC path."""
import hashlib
import json
import time

import pytest
from fastapi.testclient import TestClient

from backend.domain.engine import Engine
from backend.domain.policy import uid
from backend.settings import Profile
from backend.storage.store import Store
from backend.worker.hardware import HardwareCoordinator, verify_result
from gui_test.core.models import TestError, digest
from gui_test.tests.test_flashing import rig, TOKEN
from gui_test.execution.host import create_app
from gui_test.adapters.windows_remote import WindowsRemote


BOARD = {'host': 'fixture-pc', 'board_id': 'a', 'com': 'COM31', 'node': 'n295'}
TEMPLATE = {'single': ['python', '{tc_path}', '-p', '{com_a}'],
            'dual': ['python', '{tc_path}', '-n', '{node_a}', '-n2', '{node_b}']}
TC = {'id': 'single.py', 'path': 'single.py', 'name': 'single', 'module': '.', 'kind': 'Single',
      'timeout': 10, 'after': [], 'parser': {}, 'content_hash': 'fixture', 'disabled_reason': ''}


def good_host_result(payload):
    return {'id': payload['id'], 'runner_id': payload['runner_id'], 'request_hash': digest(payload), 'state': 'DONE',
            'terminated': True, 'outcome': 'SUCCEEDED', 'phase': 'COMPLETED',
            'flashes': [{'board': payload['connection']['a'], 'manifest_hash': digest(payload['manifest']),
                         'success': True, 'boot_ready': True,
                         'result': {'stdout': 'FLASH COMPLETE', 'stderr': '', 'exit_code': 0, 'terminated': True}}],
            'tests': [{'tc_id': 'single.py', 'state': 'PASS', 'parser': {}, 'stdout': 'Test Result: PASS\n',
                       'stderr': '', 'exit_code': 0, 'terminated': True}],
            'cases': {'boot': 'PASS', 'functional': 'PASS'}}


class Remote:
    url = 'http://fixture-runner'

    def __init__(self):
        self.identity = uid()
        self.sends = []
        self.results = {}
        self.result = None
        self.lose_response = False
        self.identity_calls = 0

    def catalog(self):
        return {'revision': 'shared-fixture', 'tests': [TC]}

    def request(self, path, method='GET', data=None):
        if path == '/identity':
            self.identity_calls += 1
            return {'runner_id': self.identity}
        if path == '/flash-tests':
            self.sends.append(data)
            self.result = good_host_result(data)
            self.results[data['id']] = self.result
            if self.lose_response:
                raise TestError('Response lost', 'DISCONNECTED')
            return self.result
        assert path.startswith('/executions/') and path.endswith('/reconcile')
        return self.results[path.split('/')[2]]


@pytest.fixture
def setup(tmp_path):
    engine = Engine(Store(tmp_path / 'job.db'), tmp_path / 'artifacts')
    profile = Profile().model_dump()
    job_id = engine.create(uid(), profile, 'fixture job', 'linux',
                           modules=[{'name': 'Bootloader', 'group': 'boot'}])['job_id']

    def finish(claim, result):
        assert engine.finish(job_id, claim['module']['id'], claim['stage'], claim['attempt']['id'],
                             claim['attempt']['token'], result)

    module_id = engine.store.snapshot(job_id)['modules'][0]['id']
    analysis = engine.claim(job_id, module_id, 'analysis', 'fixture')
    finish(analysis, {'outcome': 'SUCCEEDED', 'evidence': 'fixture analysis'})
    version = engine.store.snapshot(job_id)['version']
    engine.act(job_id, uid(), version, 'confirm', {'plan_version': 1})
    for stage in ('design', 'code'):
        claim = engine.claim(job_id, module_id, stage, 'fixture')
        result = {'outcome': 'SUCCEEDED', 'evidence': 'fixture ' + stage}
        if stage == 'code':
            result['review'] = {'tool': 'claude', 'outcome': 'PASS', 'session_id': uid(),
                                'revision': claim['job']['source_revision'], 'evidence': 'fixture review'}
        finish(claim, result)
    build = engine.claim(job_id, module_id, 'build', 'fixture')
    files = {'flash.bat': hashlib.sha256(b'fixture batch').hexdigest(),
             'image.bin': hashlib.sha256(b'fixture image').hexdigest()}
    manifest = {'schema_version': 1, 'batch': 'flash.bat', 'files': files}
    artifact = engine.artifacts / job_id / 'fixture-manifest.json'
    artifact.parent.mkdir(parents=True, exist_ok=True)
    artifact.write_text(json.dumps(manifest))
    finish(build, {'outcome': 'SUCCEEDED', 'evidence': 'fixture build',
                   'artifact': {'id': artifact.name, 'sha256': hashlib.sha256(artifact.read_bytes()).hexdigest()}})
    verification = engine.claim(job_id, module_id, 'verification', 'fixture')
    finish(verification, {'outcome': 'SUCCEEDED', 'evidence': 'fixture verification'})
    assert engine.claim(job_id, module_id, 'device_test', 'fixture')
    with engine.store.transaction() as db:
        job = engine.store.get(db, job_id)
        job['execution'] = 'bridge'
        job['session']['status'] = 'READY'
        engine.store.save(db, job, 'TEST_FIXTURE_BRIDGE_READY')
    config = {'enabled': True, 'profile': 'fixture', 'bundle': 'release',
              'connection': {'a': BOARD}, 'template': TEMPLATE,
              'cases': {'boot': ['single.py'], 'functional': ['single.py']}}
    remote = Remote()
    coordinator = HardwareCoordinator(engine, remote, {'Bootloader': config})
    return engine, job_id, module_id, remote, coordinator, config, artifact


def stage(setup):
    engine, job_id, module_id, *_ = setup
    return engine.store.snapshot(job_id)['modules'][0]['stages']['device_test']


def test_lost_post_response_reconciles_same_attempt_once(setup):
    engine, job_id, module_id, remote, coordinator, config, artifact = setup
    remote.lose_response = True
    coordinator.tick()
    pending = stage(setup)
    assert pending['status'] == 'RUNNING'
    assert pending['automation']['phase'] == 'DISPATCHING'
    assert len(remote.sends) == 1
    coordinator.tick()
    done = stage(setup)
    assert len(remote.sends) == 1
    assert done['status'] == 'SUCCEEDED' and done['result']['simulation'] is False
    assert done['result']['pipeline_id'] == done['attempts'][-1]['id']
    assert done['result']['cases'] == {'boot': 'PASS', 'functional': 'PASS'}
    assert done['result']['artifact_id'] == artifact.name
    assert engine.store.snapshot(job_id)['final_review'] is None


def test_incomplete_config_and_changed_manifest_do_not_dispatch(setup):
    engine, job_id, module_id, remote, coordinator, config, artifact = setup
    config['cases'].pop('functional')
    coordinator.tick()
    blocked = stage(setup)
    assert blocked['status'] == 'WAITING_INPUT' and blocked.get('automation_blocked')
    assert remote.sends == []
    config['cases']['functional'] = ['single.py']
    artifact.write_text('tampered')
    coordinator.tick()
    assert stage(setup)['status'] == 'WAITING_INPUT'
    assert remote.sends == []


def test_stale_baseline_is_failed_without_accepting_host_success(setup):
    engine, job_id, module_id, remote, coordinator, *_ = setup
    coordinator.tick()
    with engine.store.transaction() as db:
        job = engine.store.get(db, job_id)
        job['source_revision'] = 'changed-source-after-dispatch'
        engine.store.save(db, job, 'TEST_BASELINE_CHANGED')
    coordinator.tick()
    result = stage(setup)
    assert result['status'] == 'FAILED'
    assert result['validity'] == 'UNVERIFIED'
    assert len(remote.sends) == 1


@pytest.mark.parametrize('edit', ['wrong-id', 'wrong-hash', 'missing-boot', 'missing-tc',
                                   'false-tc-pass', 'missing-case', 'not-terminated', 'wrong-runner'])
def test_forged_or_incomplete_host_success_is_rejected(setup, edit):
    engine, job_id, module_id, remote, coordinator, config, artifact = setup
    coordinator.tick()
    result = remote.result
    if edit == 'wrong-id': result['id'] = uid()
    if edit == 'wrong-hash': result['request_hash'] = '0' * 64
    if edit == 'missing-boot': result['flashes'][0]['boot_ready'] = False
    if edit == 'missing-tc': result['tests'] = []
    if edit == 'false-tc-pass': result['tests'][0]['stdout'] = 'Test Result: FAIL\n'
    if edit == 'missing-case': result['cases'].pop('functional')
    if edit == 'not-terminated': result['terminated'] = False
    if edit == 'wrong-runner': result['runner_id'] = uid()
    coordinator.tick()
    current = stage(setup)
    assert current['status'] in {'UNKNOWN', 'RUNNING'}
    assert current['validity'] == 'UNVERIFIED'
    assert len(remote.sends) == 1


def test_host_error_does_not_mark_pass_and_releases_reservation(setup):
    engine, job_id, module_id, remote, coordinator, *_ = setup
    coordinator.tick()
    remote.result.update(outcome='FAILED', reason='FLASH_FAILED', cases={})
    coordinator.tick()
    current = stage(setup)
    assert current['status'] == 'FAILED'
    assert current['result']['outcome'] == 'FAILED'
    with engine.store.transaction() as db:
        assert not db.execute('SELECT 1 FROM leases WHERE resource=?', (coordinator.resource,)).fetchone()


def test_claim_before_send_and_tombstone_complete_failed_attempt(setup):
    engine, job_id, module_id, remote, coordinator, *_ = setup
    def lost_before_accept(path, method='GET', data=None):
        if path == '/flash-tests':
            remote.sends.append(data)
            assert stage(setup)['status'] == 'RUNNING'
            with engine.store.transaction() as db:
                assert db.execute('SELECT 1 FROM leases WHERE resource=?', (coordinator.resource,)).fetchone()
            raise TestError('Lost before accept', 'DISCONNECTED')
        if path == '/identity':
            return {'runner_id': remote.identity}
        return {'id': remote.sends[0]['id'], 'runner_id': remote.identity,
                'not_started': True, 'terminated': True, 'state': 'DONE'}
    remote.request = lost_before_accept
    coordinator.tick()
    coordinator.tick()
    current = stage(setup)
    assert current['status'] == 'FAILED'
    assert len(remote.sends) == 1


@pytest.mark.parametrize('lease_mode', ['missing', 'wrong-token'])
def test_lost_or_mismatched_lease_cannot_accept_late_success(setup, lease_mode):
    engine, job_id, module_id, remote, coordinator, *_ = setup
    coordinator.tick()
    pending = stage(setup)
    attempt = pending['attempts'][-1]
    with engine.store.transaction() as db:
        db.execute('DELETE FROM leases WHERE resource=?', (coordinator.resource,))
        if lease_mode == 'wrong-token':
            db.execute('INSERT INTO leases VALUES(?,?,?)', (coordinator.resource, attempt['id'], uid()))
    coordinator.tick()
    current = stage(setup)
    assert current['status'] == 'UNKNOWN'
    assert current['validity'] == 'UNVERIFIED'
    assert current['automation']['report']['reason'] == 'LEASE_MISMATCH'
    assert current['result'] is None


def test_endpoint_change_does_not_query_new_host_or_accept_result(setup):
    engine, job_id, module_id, remote, coordinator, config, artifact = setup
    coordinator.tick()
    replacement = Remote()
    replacement.url = 'http://different-runner'
    changed = HardwareCoordinator(engine, replacement, {'Bootloader': config})
    changed.tick()
    current = stage(setup)
    assert replacement.sends == []
    assert current['status'] == 'UNKNOWN'
    assert current['automation']['report']['reason'] == 'ENDPOINT_CHANGED'
    assert current['validity'] == 'UNVERIFIED'


def test_same_url_rebound_to_new_runner_identity_is_never_reconciled_or_resent(setup):
    engine, job_id, module_id, remote, coordinator, *_ = setup
    coordinator.tick()
    original = stage(setup)['automation']['payload']['runner_id']
    assert original == remote.identity and len(remote.sends) == 1
    remote.identity = uid()  # Same URL now reaches a different Windows runtime.
    coordinator.tick()
    current = stage(setup)
    assert current['status'] == 'UNKNOWN'
    assert current['validity'] == 'UNVERIFIED'
    assert current['automation']['report']['reason'] == 'RUNNER_CHANGED'
    assert len(remote.sends) == 1
    # Repeated ticks can only query identity, never POST or accept a tombstone.
    coordinator.tick()
    assert len(remote.sends) == 1
    assert stage(setup)['status'] == 'UNKNOWN'


def test_demo_job_is_never_auto_dispatched(setup):
    engine, job_id, module_id, remote, coordinator, *_ = setup
    with engine.store.transaction() as db:
        job = engine.store.get(db, job_id)
        job['execution'] = 'demo'
        engine.store.save(db, job, 'TEST_FIXTURE_DEMO')
    coordinator.tick()
    assert remote.sends == [] and stage(setup)['status'] == 'WAITING_INPUT'


def test_engine_attempt_to_real_http_adapter_and_fake_flash_host_end_to_end(setup, rig):
    engine, job_id, module_id, fake_remote, old_coordinator, config, artifact = setup
    host, io, flash_request, *_ = rig
    pinned = flash_request()
    artifact.write_text(json.dumps(pinned['manifest']))
    with engine.store.transaction() as db:
        job = engine.store.get(db, job_id)
        build = job['modules'][0]['stages']['build']
        build['result']['artifact']['sha256'] = hashlib.sha256(artifact.read_bytes()).hexdigest()
        engine.store.save(db, job, 'TEST_FIXTURE_PINNED_MANIFEST')
    config.update(profile='fixture', bundle='release', connection=pinned['connection'],
                  template=pinned['template'], cases=pinned['cases'])
    with TestClient(create_app(host, TOKEN), client=('127.0.0.1', 50000)) as client:
        remote = WindowsRemote('http://localhost', TOKEN, client=client)
        coordinator = HardwareCoordinator(engine, remote, {'Bootloader': config})
        coordinator.tick()
        deadline = time.monotonic() + 5
        while stage(setup)['status'] in {'RUNNING', 'UNKNOWN'} and time.monotonic() < deadline:
            coordinator.tick()
            time.sleep(.02)
        result = stage(setup)
        assert result['status'] == 'SUCCEEDED'
        assert result['result']['pipeline_id'] == result['attempts'][-1]['id']
        assert result['result']['cases'] == {'boot': 'PASS', 'functional': 'PASS'}
        assert result['automation']['payload']['runner_id'] == host.identity
        assert result['automation']['report']['flashes'][0]['serial'] == 'serial-a'
        assert sum(event[0] == 'flash' for event in io.events) == 1
        assert engine.store.snapshot(job_id)['final_review'] is None


def test_failed_pipeline_retry_keeps_history_and_clears_old_result(setup):
    engine, job_id, module_id, remote, coordinator, *_ = setup
    coordinator.tick()
    remote.result.update(outcome='FAILED', reason='FLASH_FAILED', cases={})
    coordinator.tick()
    failed = stage(setup)
    assert failed['status'] == 'FAILED'
    first_id = failed['attempts'][-1]['id']
    assert failed['attempts'][-1]['result']['outcome'] == 'FAILED'
    engine.act(job_id, uid(), engine.store.snapshot(job_id)['version'], 'retry',
               {'module_id': module_id, 'stage': 'device_test', 'previous_attempt_id': first_id})
    next_claim = engine.claim(job_id, module_id, 'device_test', 'fixture')
    assert next_claim and next_claim['attempt']['id'] != first_id
    waiting = stage(setup)
    assert waiting['status'] == 'WAITING_INPUT' and waiting['result'] is None
    assert waiting['attempts'][0]['result']['outcome'] == 'FAILED'
    assert waiting['attempts'][0]['automation']['payload']['id'] == first_id
    coordinator.tick()
    coordinator.tick()
    current = stage(setup)
    assert current['status'] == 'SUCCEEDED'
    assert [payload['id'] for payload in remote.sends] == [first_id, next_claim['attempt']['id']]
    assert current['attempts'][0]['result']['outcome'] == 'FAILED'
    assert current['attempts'][1]['result']['outcome'] == 'SUCCEEDED'
    assert engine.store.snapshot(job_id)['final_review'] is None


def test_manifest_helper_writes_reviewable_hashes_once_outside_image_root(rig, tmp_path):
    from scripts.create_flash_manifest import create_manifest
    host, io, request, images, *_ = rig
    output = tmp_path / 'artifact' / 'flash-manifest.json'
    manifest = create_manifest(images, 'flash.bat', output)
    assert manifest == request()['manifest']
    assert output.is_file()
    with pytest.raises(FileExistsError):
        create_manifest(images, 'flash.bat', output)
    with pytest.raises(ValueError):
        create_manifest(images, 'flash.bat', images / 'manifest.json')
    assert io.events == []
