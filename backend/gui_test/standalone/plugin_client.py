"""Reference bsp-upgrade host adapter. It never owns or stops the backend process."""
import json
from pathlib import Path
import re
import subprocess
import time
from urllib.parse import urlsplit

import httpx
from ..core.integration import CONTRACT_VERSION, resolve_patterns
from ..core.models import TestError
from ..core.diagnostics import DiagnosticRecorder


class SystemdService:
    """Installed unit, fixed argv, no shell; lifecycle outlives plugin requests."""
    def __init__(self, unit='bsp-gui-test.service', *, user=False):
        if not re.fullmatch(r'[A-Za-z0-9_.@-]+\.service', unit):
            raise ValueError('Expected an installed systemd service unit')
        self.unit, self.user = unit, user

    def start(self):
        subprocess.run(['systemctl', *(['--user'] if self.user else []), 'start', self.unit],
                       check=True, timeout=30, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                       stderr=subprocess.DEVNULL, shell=False)


class PluginClient:
    def __init__(self, url, token, expected_identity, *, client=None, starter=None, clock=time.monotonic, sleep=time.sleep,
                 log_dir=None, diagnostic_callback=None, diagnostics=None):
        parsed = urlsplit(url)
        if (parsed.scheme != 'http' or parsed.hostname not in {'localhost', '127.0.0.1'} or parsed.path not in {'', '/'} or
                parsed.username or parsed.password or parsed.query or parsed.fragment or len(token) < 32):
            raise ValueError('Use the authenticated loopback service endpoint')
        self.url, self.token, self.expected = url.rstrip('/'), token, dict(expected_identity)
        required = {'runtime_id', 'package_version', 'config_revision', 'runner_id'}
        if not required <= self.expected.keys():
            raise ValueError('Pin runtime/package/config/runner identity')
        self.client = client or httpx.Client(timeout=5, follow_redirects=False, trust_env=False)
        self.starter, self.clock, self.sleep = starter, clock, sleep
        self.diagnostics = diagnostics or DiagnosticRecorder(log_dir, diagnostic_callback)
        self.last_diagnostic = None

    def _diagnostic_error(self, code, phase, cause, hint, *, started=None, attempt=1, correlation_id=None, status=503):
        self.last_diagnostic = self.diagnostics.record(phase, self.url, code, cause, hint, attempt=attempt,
            duration_ms=(self.clock() - started) * 1000 if started is not None else 0, correlation_id=correlation_id)
        error = TestError(cause + ' ' + hint, code, status)
        error.diagnostic = self.last_diagnostic
        return error

    def request(self, method, path, body=None, key=None, *, diagnostic_attempt=1, correlation_id=None):
        headers = {'Authorization': 'Bearer ' + self.token, 'X-Bsp-Client': 'dashboard'}
        if key is not None:
            if not isinstance(key, str) or not 1 <= len(key) <= 180:
                raise ValueError('Reuse a stable idempotency key for one execution intent')
            headers['Idempotency-Key'] = key
        started = self.clock()
        try:
            response = self.client.request(method, self.url + path, headers=headers,
                                           **({'json': body} if body is not None else {}))
        except httpx.TransportError:
            raise self._diagnostic_error('SERVICE_CONNECTION_FAILED', 'backend-connect', 'GUI Test backend connection failed.',
                'Check the installed service, loopback port and service logs; retry with the same request key.',
                started=started, attempt=diagnostic_attempt, correlation_id=correlation_id) from None
        if response.status_code not in {200, 202}:
            code = 'SERVICE_AUTH_FAILED' if response.status_code in {401, 403} else 'INTEGRATION_REJECTED'
            raise self._diagnostic_error(code, 'backend-auth' if code == 'SERVICE_AUTH_FAILED' else 'backend-request',
                'GUI Test backend rejected the request.', 'Check service credentials and the matching integration configuration.',
                started=started, attempt=diagnostic_attempt, correlation_id=correlation_id, status=response.status_code)
        try:
            return response.json()
        except ValueError:
            raise self._diagnostic_error('SERVICE_RESPONSE_INVALID', 'backend-response', 'GUI Test returned an invalid response.',
                'Check that the configured port belongs to the matching GUI Test package.', started=started,
                attempt=diagnostic_attempt, correlation_id=correlation_id) from None

    def connector_inventory(self):
        # Discovery stays usable before TC/flash execution defaults are ready.
        value = self.request('GET', '/api/v1/gui-test/live/connector/inventory')
        if value.get('runner_id') != self.expected['runner_id']:
            raise TestError('Connector identity mismatch', 'RUNNER_CHANGED')
        return value

    def board_console(self):
        # Read-only discovery; execution still uses strict health/preparation pins.
        value = self.request('GET', '/api/v1/gui-test/live/connector/console')
        if value.get('runner_id') != self.expected['runner_id']:
            raise TestError('Console identity mismatch', 'RUNNER_CHANGED')
        return value

    def connector_errors(self, after=0):
        if type(after) is not int or after < 0: raise ValueError('Invalid error cursor')
        return self.request('GET', '/api/v1/gui-test/live/connector/errors?after=' + str(after))

    def health(self, *, attempt=1, correlation_id=None):
        started = self.clock()
        health = self.request('GET', '/api/v1/health', diagnostic_attempt=attempt, correlation_id=correlation_id)
        if health.get('integration_contract_version') != CONTRACT_VERSION or any(health.get(k) != v for k, v in self.expected.items()):
            raise self._diagnostic_error('SERVICE_IDENTITY_MISMATCH', 'backend-identity',
                'Existing service identity/configuration does not match this plugin.',
                'Check runtime, package, contract, config and Runner identity; use the installed matching service.', started=started,
                attempt=attempt, correlation_id=correlation_id)
        if not health.get('service_instance_id') or type(health.get('worker_epoch')) is not int or not health.get('worker_running'):
            raise self._diagnostic_error('SERVICE_NOT_READY', 'backend-worker', 'GUI worker is not ready.',
                'Check the worker OS lock and service startup/recovery logs.', started=started,
                attempt=attempt, correlation_id=correlation_id)
        self.last_diagnostic = self.diagnostics.record('backend-ready', self.url, 'READY', 'GUI Test service identity and worker verified.',
            'Use existing Run ID/key when reconnecting.', attempt=attempt, duration_ms=(self.clock() - started) * 1000,
            correlation_id=correlation_id)
        return health

    def ensure_service(self, timeout=30):
        from uuid import uuid4
        correlation = uuid4().hex
        try:
            return self.health(correlation_id=correlation)
        except TestError as exc:
            if exc.code != 'SERVICE_CONNECTION_FAILED':
                raise
            if self.starter is None:
                raise
        # Identity/authentication failures never start a second competing service.
        try:
            self.starter.start()
        except Exception:
            raise self._diagnostic_error('SERVICE_START_FAILED', 'backend-start', 'Installed GUI Test service could not be started.',
                'Check the installed service name, service-account permissions and supervisor logs.', correlation_id=correlation) from None
        deadline = self.clock() + timeout
        attempt = 2
        while self.clock() < deadline and attempt <= 6:
            try:
                return self.health(attempt=attempt, correlation_id=correlation)
            except TestError as exc:
                if exc.code not in {'SERVICE_CONNECTION_FAILED', 'SERVICE_NOT_READY'}:
                    raise
                self.sleep(min(2 ** (attempt - 2), 8, max(0, deadline - self.clock())))
                attempt += 1
        raise self._diagnostic_error('SERVICE_NOT_READY', 'backend-start', 'Installed service did not become ready.',
            'Inspect service startup, worker recovery and connection logs at the diagnostic path.', attempt=attempt - 1,
            correlation_id=correlation)

    def preview(self, installer_path, patterns):
        return self.request('POST', '/api/v1/gui-test/live/integration/preview',
                            {'installer_path': installer_path, 'tc_patterns': patterns})

    def browser_access(self):
        """Short-lived read-only bootstrap URL, containing no service credential."""
        value = self.request('POST', '/api/v1/gui-test/live/integration/browser-session')
        return value | {'url': self.url + value['path']}

    def connect(self, timeout=30):
        """Connect/doctor hook for a plugin status panel; never claims hardware."""
        backend = self.ensure_service(timeout)
        started = self.clock()
        capabilities = self.request('GET', '/api/v1/gui-test/live/capabilities')
        connection = capabilities.get('connection', {})
        if not connection.get('ready'):
            error = self._diagnostic_error('RUNNER_UNAVAILABLE', 'runner-connect', 'TEST BOARD CONNECTOR connection is not ready.',
                'Check the TEST BOARD CONNECTOR service, SSH tunnel, token and matching capability version.', started=started)
            remote = connection.get('diagnostic')
            if isinstance(remote, dict):
                error.diagnostic['backend_diagnostic'] = {k: remote[k] for k in ('correlation_id', 'code', 'phase', 'log_path', 'log_error') if k in remote}
            raise error
        event = self.diagnostics.record('runner-ready', self.url, 'READY', 'Backend reports the TEST BOARD CONNECTOR connection ready.',
            'Board boot and TC readiness are checked separately during preparation.', duration_ms=(self.clock() - started) * 1000)
        self.last_diagnostic = event
        return {'backend': backend, 'runner': connection, 'diagnostic': event}

    def preparation(self, preparation_id):
        if not re.fullmatch('[a-f0-9]{32}', preparation_id):
            raise ValueError('Invalid preparation ID')
        return self.request('GET', '/api/v1/gui-test/live/integration/preparations/' + preparation_id)

    def start(self, key, installer_path, patterns, prepared_token=None):
        body = {'installer_path': installer_path, 'tc_patterns': patterns}
        if prepared_token is not None:
            body['prepared_token'] = prepared_token
        return self.request('POST', '/api/v1/gui-test/live/integration/runs', body, key)

    def run(self, run_id):
        if not re.fullmatch('[a-f0-9]{32}', run_id):
            raise ValueError('Invalid Run ID')
        value = self.request('GET', '/api/v1/gui-test/live/runs/' + run_id)
        diagnostic = value.get('integration', {}).get('diagnostic')
        if isinstance(diagnostic, dict):
            self.last_diagnostic = self.diagnostics.record('run-connection', self.url, diagnostic.get('code', 'RUNNER_UNAVAILABLE'),
                'Backend recorded a connection/preparation failure for this Run.',
                'Inspect the Run reason and linked backend/Runner diagnostic; reconnect using the same Run ID.')
            self.last_diagnostic['backend_diagnostic'] = {k: diagnostic[k] for k in ('correlation_id', 'code', 'phase', 'log_path', 'log_error') if k in diagnostic}
        return value


class PatternDefaults:
    """Plugin-owned defaults; per-execution edits are never implicitly saved."""
    def __init__(self, path):
        self.path = Path(path)

    def read(self):
        return json.loads(self.path.read_text(encoding='utf-8')) if self.path.exists() else {'modules': {}, 'global': []}

    def suggest(self, module_key, override=None):
        value = self.read()
        return resolve_patterns(module_key, value['modules'], value['global'], override)

    def save(self, module_key, patterns):
        from ..core.integration import validate_patterns
        # A plugin host with concurrent settings writers should inject its own
        # transactional configuration store instead of this single-writer example.
        value = self.read()
        patterns = validate_patterns(patterns)
        if module_key is None:
            value['global'] = patterns
        else:
            value['modules'][module_key] = patterns
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(self.path.suffix + '.tmp')
        temporary.write_text(json.dumps(value, indent=2), encoding='utf-8')
        temporary.replace(self.path)
