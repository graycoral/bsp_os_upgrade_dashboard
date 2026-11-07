"""Connection failures remain visible before any Run or hardware request exists."""
import json

import httpx
import pytest

from backend.gui_test.adapters.windows_remote import WindowsRemote
from backend.gui_test.core.diagnostics import DiagnosticRecorder
from backend.gui_test.core.models import TestError
from backend.gui_test.standalone.plugin_client import PluginClient


TOKEN = 'never-log-this-connection-token-0123456789'
IDENTITY = {'runtime_id': 'runtime', 'package_version': '0.1.0', 'config_revision': 'cfg', 'runner_id': 'runner'}


def events(path):
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]


@pytest.mark.parametrize('failure,code', [('refused', 'SERVICE_CONNECTION_FAILED'),
    ('timeout', 'SERVICE_CONNECTION_FAILED'), ('auth', 'SERVICE_AUTH_FAILED')])
def test_plugin_failure_is_reported_and_logged_locally_when_backend_is_unreachable(tmp_path, failure, code):
    seen, requests = [], []
    def transport(request):
        requests.append(request)
        if failure == 'auth': return httpx.Response(401, json={'message': 'secret=' + TOKEN})
        error = httpx.ConnectError if failure == 'refused' else httpx.ReadTimeout
        raise error('password=private-password Bearer ' + TOKEN, request=request)
    with httpx.Client(transport=httpx.MockTransport(transport)) as http:
        plugin = PluginClient('http://127.0.0.1:8767', TOKEN, IDENTITY, client=http,
                              log_dir=tmp_path / 'plugin-logs', diagnostic_callback=seen.append)
        with pytest.raises(TestError) as error:
            plugin.connect()
    assert error.value.code == code
    assert len(requests) == 1 and requests[0].method == 'GET'
    diagnostic = error.value.diagnostic
    assert diagnostic['correlation_id'] and diagnostic['at'].endswith('+00:00')
    assert diagnostic['duration_ms'] >= 0 and diagnostic['attempt'] == 1
    assert diagnostic['hint'] and diagnostic['phase'].startswith('backend-')
    persisted = events(tmp_path / 'plugin-logs/connections.jsonl')
    assert persisted[-1]['code'] == code and seen[-1]['correlation_id'] == diagnostic['correlation_id']
    assert TOKEN not in str(persisted) + str(seen) + str(error.value)
    assert 'private-password' not in str(persisted) + str(seen)


def test_backend_start_retries_are_bounded_backed_off_and_share_correlation(tmp_path):
    clock = [0.0]
    delays, requests, starts = [], [], []
    def sleep(seconds):
        delays.append(seconds); clock[0] += seconds
    def transport(request):
        requests.append(request)
        raise httpx.ConnectError('unreachable', request=request)
    class Starter:
        def start(self): starts.append('started')
    with httpx.Client(transport=httpx.MockTransport(transport)) as http:
        plugin = PluginClient('http://127.0.0.1:8767', TOKEN, IDENTITY, client=http, starter=Starter(),
                              log_dir=tmp_path / 'logs', clock=lambda: clock[0], sleep=sleep)
        with pytest.raises(TestError) as error:
            plugin.ensure_service(timeout=30)
    assert error.value.code == 'SERVICE_NOT_READY'
    assert starts == ['started'] and len(requests) <= 6
    assert delays == sorted(delays) and max(delays) <= 8
    recorded = events(tmp_path / 'logs/connections.jsonl')
    assert len({event['correlation_id'] for event in recorded}) == 1
    assert max(event['attempt'] for event in recorded) <= 6
    assert all(request.method == 'GET' for request in requests)


@pytest.mark.parametrize('failure,code', [('refused', 'RUNNER_UNAVAILABLE'),
    ('timeout', 'RUNNER_UNAVAILABLE'), ('auth', 'RUNNER_AUTH_REQUIRED')])
def test_backend_to_runner_failure_has_durable_actionable_diagnostic_without_hardware_command(tmp_path, failure, code):
    seen, calls = [], []
    recorder = DiagnosticRecorder(tmp_path / 'runner-logs', seen.append)
    def transport(request):
        calls.append(request)
        if failure == 'auth': return httpx.Response(401, json={'message': TOKEN})
        error = httpx.ConnectError if failure == 'refused' else httpx.ReadTimeout
        raise error('secret=' + TOKEN, request=request)
    with httpx.Client(transport=httpx.MockTransport(transport)) as http:
        remote = WindowsRemote('http://127.0.0.1:8768', TOKEN, client=http, diagnostics=recorder)
        status = remote.readiness()
    assert status['ready'] is False and status['diagnostic']['code'] == code
    assert status['diagnostic']['correlation_id'] and status['diagnostic']['hint']
    assert len(calls) == 1 and calls[0].url.path == '/v1/identity'
    assert calls[0].method == 'GET'
    assert events(recorder.path)[-1]['code'] == code
    assert seen and TOKEN not in recorder.path.read_text(encoding='utf-8')


def test_diagnostic_log_write_failure_does_not_replace_original_connection_error(tmp_path):
    blocked = tmp_path / 'not-a-directory'; blocked.write_text('fixture')
    seen = []
    def transport(request): raise httpx.ConnectError('password=do-not-expose', request=request)
    with httpx.Client(transport=httpx.MockTransport(transport)) as http:
        plugin = PluginClient('http://127.0.0.1:8767', TOKEN, IDENTITY, client=http,
                              log_dir=blocked / 'logs', diagnostic_callback=seen.append)
        with pytest.raises(TestError) as error:
            plugin.ensure_service()
    assert error.value.code == 'SERVICE_CONNECTION_FAILED'
    assert error.value.diagnostic['log_error'] == 'DIAGNOSTIC_LOG_UNAVAILABLE'
    assert seen[-1]['code'] == 'SERVICE_CONNECTION_FAILED'
    assert 'do-not-expose' not in str(error.value.diagnostic)


def test_diagnostic_redacts_credential_urls_queries_headers_and_rotates_bounded_files(tmp_path):
    recorder = DiagnosticRecorder(tmp_path / 'logs', max_bytes=600, backups=2)
    secrets = ['url-user', 'url-password', 'query-secret', 'header-secret', 'environment-secret']
    for index in range(12):
        recorder.record('backend-connect', 'https://url-user:url-password@example.test/private?token=query-secret',
                        'FAILED', 'Authorization=header-secret token=environment-secret',
                        'Bearer header-secret https://url-user:url-password@example.test/?password=query-secret', attempt=index + 1)
    files = list(recorder.directory.glob('connections.jsonl*'))
    assert 1 <= len(files) <= 3
    text = ''.join(path.read_text(encoding='utf-8') for path in files)
    assert all(secret not in text for secret in secrets)
    assert all(row['target'] == 'https://example.test' for row in events(recorder.path))
