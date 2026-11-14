"""Full Agent Monitor BSP facade; the existing Engine and Worker keep ownership."""
import re
from urllib.parse import urlencode

from .plugin_client import PluginClient


def bsp_scope_allowed(path, method):
    if path == '/api/v1/config':
        return method in {'GET', 'PUT'}
    if path == '/api/v1/config/validate':
        return method == 'POST'
    if path == '/api/v1/jobs':
        return method in {'GET', 'POST'}
    if method == 'GET':
        return bool(re.fullmatch(r'/api/v1/jobs/[a-f0-9]{32}(?:/(?:events|modules/[a-f0-9]{32}|reports(?:/[a-f0-9]{32})?|orchestration(?:/[a-z-]+(?:/[a-f0-9]{32})?)?|decision-candidates(?:/[a-f0-9]{32})?|scope-holds(?:/[a-f0-9]{32})?))?', path))
    return method == 'POST' and bool(re.fullmatch(r'/api/v1/jobs/[a-f0-9]{32}/actions/[a-z-]+', path))


class BspPluginClient(PluginClient):
    """Explicit full-host scope. GUI-only standalone servers reject this scope."""
    service_scope = 'bsp-control-v1'

    def bsp_settings(self):
        return self.request('GET', '/api/v1/config')

    def save_bsp_settings(self, value):
        return self.request('PUT', '/api/v1/config', value)

    def validate_bsp_settings(self, value):
        return self.request('POST', '/api/v1/config/validate', value)

    def jobs(self):
        return self.request('GET', '/api/v1/jobs')

    @staticmethod
    def _job_path(job_id):
        if not isinstance(job_id, str) or not re.fullmatch('[a-f0-9]{32}', job_id):
            raise ValueError('Invalid Job ID')
        return '/api/v1/jobs/' + job_id

    def start_job(self, key, *, title='BSP OS Upgrade', mode='linux'):
        return self.request('POST', '/api/v1/jobs', {'title': title, 'mode': mode}, key)

    def job(self, job_id):
        return self.request('GET', self._job_path(job_id))

    def job_action(self, job_id, action, *, key, expected_version, data=None):
        if not isinstance(action, str) or not re.fullmatch('[a-z-]{1,80}', action):
            raise ValueError('Invalid Job action')
        return self.request('POST', self._job_path(job_id) + '/actions/' + action,
                            {'expected_version': expected_version, 'data': data or {}}, key)

    def job_events(self, job_id, after=0):
        if type(after) is not int or after < 0:
            raise ValueError('Invalid event cursor')
        return self.request('GET', self._job_path(job_id) + '/events?' + urlencode({'after': after}))

    def job_reports(self, job_id):
        return self.request('GET', self._job_path(job_id) + '/reports')

    def job_orchestration(self, job_id):
        return self.request('GET', self._job_path(job_id) + '/orchestration')
