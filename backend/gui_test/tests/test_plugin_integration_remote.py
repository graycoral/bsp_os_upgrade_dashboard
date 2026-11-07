"""Actual WindowsRemote/Runner HTTP contract; hardware and process execution are fake."""
import time

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.gui_test.adapters.windows_remote import WindowsRemote
from backend.gui_test.core.diagnostics import DiagnosticRecorder
from backend.gui_test.core.integration_sources import prepare_inputs
from backend.gui_test.core.models import uid, digest
from backend.gui_test.execution.host import create_app
from backend.gui_test.tests.test_flashing import FakeIO, TEMPLATE, rig
from backend.gui_test.tests.test_plugin_integration_pipeline import batch_rig


@pytest.mark.parametrize('lost_reply', [False, True])
def test_windows_remote_upload_prepare_reconcile_child_and_release_use_one_batch_over_http(rig, batch_rig, tmp_path, lost_reply):
    host, io, unused_parent, _ = batch_rig
    _, _, request, images, source, _ = rig
    host.batches.release(unused_parent['id'], {'token': unused_parent['token'], 'epoch': unused_parent['epoch']})
    receipt = prepare_inputs({'installer_path': str(images / 'flash.bat')},
        {'installer_roots': [str(images.parent)], 'tc_root': str(source)}, tmp_path / 'prepared')
    run_id = uid()
    def flash(*args):
        value = FakeIO.flash(io, *args)
        observer = host.flashing.observers[run_id][0]
        observer.feed(b'BOOT START\n'); observer.feed(b'BOOT_READY')
        return value
    io.flash = flash
    children = []
    def execute(item, directory, timeout):
        children.append(item['id'])
        item.update(state='DONE', terminated=True, exit_code=0, stdout='Test Result: PASS\n', stderr='')
        host.save(item)
    host.execute = execute
    saved = []
    with TestClient(create_app(host, 'runner-http-fixture-token-0123456789abcdef'), client=('127.0.0.1', 1000)) as client:
        class Transport:
            lost = False
            def request(self, method, url, **kwargs):
                response = client.request(method, url, **kwargs)
                if lost_reply and not self.lost and method == 'POST' and url.endswith('/prepare'):
                    self.lost = True
                    raise httpx.ReadTimeout('Preparation accepted but reply lost')
                return response
        remote = WindowsRemote('http://127.0.0.1', 'runner-http-fixture-token-0123456789abcdef',
                               client=Transport(), diagnostics=DiagnosticRecorder(tmp_path / 'diagnostics'))
        context = {'run_id': run_id, 'connection': request()['connection'], 'command_template': TEMPLATE,
                   'config': {'runner_id': host.identity, 'flash_profile': 'fixture',
                              'flash_profile_revision': remote.integration_profile('fixture')['revision']}, 'save_batch': saved.append}
        initial = remote.begin_integration(receipt, context)
        assert initial['state'] == ('UNKNOWN' if lost_reply else 'RUNNING')
        assert len(saved) == 1 and saved[0]['batch_id'] == run_id
        deadline = time.monotonic() + 4
        while time.monotonic() < deadline:
            ready = remote.reconcile_integration(run_id, initial)
            if ready['state'] == 'READY': break
            time.sleep(.01)
        assert ready['state'] == 'READY', ready
        assert host.batches.status(run_id)['state'] == 'READY'
        # A duplicate delivery after response loss keeps the original prepare ID.
        replay = remote.begin_integration(receipt, context)
        assert replay['prepare_id'] == initial['prepare_id']
        assert sum(event[0] == 'flash' for event in io.events) == 1
        tc = next(test for test in receipt['catalog']['tests'] if test['id'] == 'single.py')
        output = []
        result = remote.execute(tc, context['connection'], 2,
            {'process_ref': 'windows:' + uid(), 'source_revision': receipt['source_snapshot']['source_revision'],
             'command_template': TEMPLATE, 'source_snapshot': receipt['source_snapshot'],
             'source_directory': receipt['source_directory'], 'integration_batch': ready},
            lambda stream, text: output.append((stream, text)), lambda: False)
        assert result['terminated'] is True and result['exit_code'] == 0
        assert children and ('stdout', 'Test Result: PASS\n') in output
        assert remote.finish_integration(ready)['state'] == 'RELEASED'
        assert sum(event[0] == 'flash' for event in io.events) == 1


@pytest.mark.parametrize('panic', [True, False])
def test_remote_preserves_unsafe_console_verdict_without_copying_raw_console_into_result(tmp_path, panic):
    posted = []
    execution_id = uid()
    def transport(request):
        import json
        if request.url.path == '/v1/executions':
            posted.append(json.loads(request.content))
            return httpx.Response(200, json={'id': execution_id, 'state': 'RUNNING'})
        return httpx.Response(200, json={'id': execution_id, 'state': 'DONE', 'source_revision': 'fixed-source',
            'request_hash': digest(posted[0]), 'terminated': True, 'exit_code': 0,
            'stdout': 'Test Result: PASS\n', 'stderr': '',
            'console': {'unsafe': True, 'observers': [{'panic': panic, 'complete': panic,
                'tail': 'private-raw-console-payload', 'text': 'private-raw-console-payload'}]}})
    with httpx.Client(transport=httpx.MockTransport(transport)) as http:
        remote = WindowsRemote('http://127.0.0.1:8768', 'runner-http-fixture-token-0123456789abcdef',
                               client=http, diagnostics=DiagnosticRecorder(tmp_path / 'diagnostics'))
        result = remote.execute({'id': 'case', 'path': 'case.py', 'kind': 'Single'},
            {'a': {'host': 'fixture', 'board_id': 'a', 'com': 'COM31'}}, 1,
            {'process_ref': 'windows:' + execution_id, 'source_revision': 'fixed-source', 'command_template': TEMPLATE},
            lambda *args: None, lambda: False)
    assert result.get('console_failure') or result.get('panic') or result.get('observation_gap'), result
    assert 'private-raw-console-payload' not in str(result)
