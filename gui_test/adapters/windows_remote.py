"""Linux-side adapter for a Windows host reached over an SSH reverse tunnel."""
import time
from urllib.parse import urlsplit
import httpx
from gui_test.core.models import TestError, Connection, digest


class WindowsRemote:
    simulation = False
    branches = ['shared']

    def __init__(self, url, token, client=None):
        parsed = urlsplit(url)
        if parsed.scheme != 'http' or parsed.hostname not in {'127.0.0.1', 'localhost'} or parsed.username or parsed.password or parsed.path not in {'', '/'} or parsed.query or parsed.fragment:
            raise ValueError('Windows runner URL must be an HTTP loopback SSH tunnel endpoint')
        if len(token) < 32: raise ValueError('Set GUI_TEST_RUNNER_TOKEN in both Dashboard API and worker environments')
        self.url = url.rstrip('/')
        self.token = token
        self.client = client or httpx.Client(timeout=5, follow_redirects=False, trust_env=False)

    def request(self, path, method='GET', data=None):
        try:
            response = self.client.request(method, self.url + '/v1' + path,
                headers={'Authorization': 'Bearer ' + self.token}, **({'json': data} if data is not None else {}))
            if response.status_code >= 400:
                raise TestError('Windows runner rejected the request; check source, COM mapping, command and active executions', 'RUNNER_REJECTED')
            if response.status_code != 200 or len(response.content) > 2 * 1024 * 1024:
                raise ValueError('Invalid runner response')
            return response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise TestError('Windows runner is unavailable; check the runner and SSH tunnel', 'RUNNER_UNAVAILABLE') from exc

    def catalog(self, branch='shared'):
        if branch not in {'shared', 'demo/main'}: raise TestError('Use the configured shared TC source')
        return self.request('/catalog')

    def boards(self): return self.request('/boards')['boards']

    def verify(self, connection, dual):
        value = dict(connection)
        if not dual: value['b'] = None
        self.request('/verify', 'POST', value)

    def probe(self, process_ref):
        if not process_ref.startswith('windows:'): return 'UNKNOWN'
        try:
            value = self.request('/executions/' + process_ref.split(':', 1)[1] + '/reconcile', 'POST')
            return 'STOPPED' if value.get('terminated') is True else 'UNKNOWN'
        except TestError: return 'UNKNOWN'

    def execute(self, tc, connections, timeout, context, emit, cancelled):
        identity = context['process_ref'].split(':', 1)[1]
        path = '/executions/' + identity
        payload = {'id': identity, 'tc_id': tc['id'], 'source_revision': context['source_revision'],
                   'connection': Connection.model_validate(connections).model_dump(), 'template': context['command_template']}
        offsets = {'stdout': 0, 'stderr': 0}
        try:
            try: self.request('/executions', 'POST', payload)
            except TestError:
                # An HTTP failure is not evidence that the TC did not start. Never resubmit.
                self.request(path)
            deadline = time.monotonic() + timeout + 20
            while time.monotonic() < deadline:
                value = self.request(path + ('/cancel' if cancelled() else '/poll'), 'POST')
                if value.get('id') != identity or value.get('source_revision') != context['source_revision'] or value.get('request_hash') != digest(payload):
                    raise TestError('Runner response does not match this attempt', 'RUNNER_MISMATCH')
                for stream in offsets:
                    text = value.get(stream, '')
                    if not isinstance(text, str) or len(text) < offsets[stream] or len(text.encode()) > 262144:
                        raise TestError('Invalid runner log snapshot')
                    emit(stream, text[offsets[stream]:]); offsets[stream] = len(text)
                if value.get('state') in {'DONE', 'UNKNOWN'}:
                    # Configured COM mapping is not proof of physical board/image identity.
                    result = {key: value[key] for key in ('exit_code', 'terminated', 'forced_state') if key in value}
                    result['executed_command_argv'] = value.get('argv')
                    return result
                time.sleep(.1)
            self.request(path + '/cancel', 'POST')
        except TestError:
            pass
        return {'exit_code': None, 'terminated': False}
