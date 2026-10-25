from concurrent.futures import ThreadPoolExecutor
from gui_test.core.models import TestError


class Worker:
    def __init__(self, manager):
        self.manager = manager
        self.pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix='gui-test')
        self.pending = {}

    def execute(self, claim):
        m = self.manager
        run, a = claim['run'], claim['attempt']
        return m.runner.execute(claim['tc'], run['connection_snapshot'], claim['tc']['timeout'], claim['context'],
                                lambda stream, text: m.emit(run['id'], a['id'], stream, text),
                                lambda: m.get(run['id'])['state'] == 'CANCEL_REQUESTED')

    def tick(self):
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
            if len(self.pending) >= 4:
                break
            claim = self.manager.claim(run['id'])
            if claim:
                self.pending[self.pool.submit(self.execute, claim)] = claim
        self.manager.sync_one()

    def close(self):
        self.pool.shutdown(wait=True)
        for future, claim in self.pending.items():
            try:
                self.manager.finish(claim, future.result())
            except Exception:
                pass  # persisted RUNNING is reconciled at next manager startup
        self.pending.clear()
