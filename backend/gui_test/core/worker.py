from concurrent.futures import ThreadPoolExecutor
from .models import TestError


class Worker:
    def __init__(self, manager):
        self.manager = manager
        self.pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix='gui-test')
        self.pending = {}
        self.preparing = {}

    def execute(self, claim):
        m = self.manager
        run, a = claim['run'], claim['attempt']
        return m.runner.execute(claim['tc'], run['connection_snapshot'], claim['tc']['timeout'], {**claim['context'], 'report_target': lambda target: m.record_target(run['id'], a['id'], target), 'report_usage': lambda sequence, usage: m.record_usage(run['id'], a['id'], sequence, usage)},
                                lambda stream, text: m.emit(run['id'], a['id'], stream, text),
                                lambda: m.get(run['id'])['state'] == 'CANCEL_REQUESTED')

    def tick(self):
        integration = getattr(self.manager, 'integration', None)
        for future, identity in list(self.preparing.items()):
            if future.done():
                try:
                    future.result()
                except Exception:
                    pass  # persisted receipt is reconciled; never infer termination
                del self.preparing[future]
        for future, claim in list(self.pending.items()):
            if future.done():
                try:
                    result = future.result()
                except Exception:
                    # An adapter exception is not evidence that its process terminated.
                    result = {'exit_code': None, 'terminated': False}
                self.manager.finish(claim, result)
                del self.pending[future]
        for run in self.manager.store.all():
            if integration and run.get('integration'):
                active = set(self.preparing.values())
                meta = run['integration']
                task = None
                if meta.get('pending_terminal_state') and not meta.get('batch_released'):
                    if meta.get('finalization_retry_at', 0) <= integration.clock():
                        task = integration.finalize_run
                elif run['state'] == 'QUEUED' and meta['phase'] == 'PREPARING':
                    task = integration.prepare_run
                elif meta['phase'] == 'WAITING_BATCH' or (run['state'] == 'UNKNOWN' and meta.get('batch')):
                    task = integration.poll_batch
                elif run['state'] in {'COMPLETED', 'CANCELLED'} and meta.get('batch') and not meta.get('batch_released'):
                    task = integration.release_batch
                if task and run['id'] not in active and len(self.preparing) < 4:
                    self.preparing[self.pool.submit(task, run['id'])] = run['id']
            if len(self.pending) >= 4:
                break
            claim = self.manager.claim(run['id'])
            if claim:
                self.pending[self.pool.submit(self.execute, claim)] = claim
        self.manager.sync_one()
        if integration and 'preview' not in self.preparing.values() and len(self.preparing) < 4:
            self.preparing[self.pool.submit(integration.prepare_one)] = 'preview'

    def close(self):
        self.pool.shutdown(wait=True)
        for future, claim in self.pending.items():
            try:
                self.manager.finish(claim, future.result())
            except Exception:
                pass  # persisted RUNNING is reconciled at next manager startup
        self.pending.clear()
