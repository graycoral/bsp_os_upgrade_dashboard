"""Reusable plugin-side callback consumer. No bundled model or shell execution.

request(method, path, payload) is the host's authenticated JSON transport. An
exception leaves the lease unacknowledged so another consumer can redeliver it.
The analyzer receives persisted evidence, and must return AnalysisResult fields.
"""
from ..core.failure_analysis import AnalysisResult

BASE = '/api/v1/gui-test/live/integration/analyses'


class AnalysisWorker:
    def __init__(self, request, analyzer, *, consumer='plugin-analysis', lease_seconds=60):
        self.request, self.analyzer = request, analyzer
        self.consumer, self.lease_seconds = consumer, lease_seconds

    def tick(self):
        receipt = self.request('POST', BASE + '/claim', {'consumer': self.consumer, 'lease_seconds': self.lease_seconds})
        item = receipt.get('analysis')
        if item is None:
            return None
        result = AnalysisResult.model_validate(self.analyzer(item)).model_dump()
        return self.request('POST', BASE + '/' + item['id'] + '/submit',
                            {'lease_token': item['lease_token'], 'result': result})
