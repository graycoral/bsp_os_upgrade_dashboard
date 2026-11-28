"""Existing Dashboard process owns one GUI worker/lock per physical store."""
import os
import time
from ..core.worker import Worker
from ..standalone.server import ProcessLock
from ..standalone.integration import ServiceRegistry


class DashboardWorkers:
    def __init__(self, managers, runtime):
        self.entries = []
        seen = set()
        try:
            for manager in managers:
                path = manager.store.path.resolve()
                if path in seen: continue
                seen.add(path)
                lock = ProcessLock(path.with_suffix('.lock')); lock.__enter__()
                self.entries.append([manager, lock, None, False])
                if getattr(manager, 'integration', None) is not None:
                    ServiceRegistry(manager, runtime, os.environ.get('GUI_TEST_INTEGRATION_PRINCIPAL', 'bsp-upgrade')).start()
                manager.recover(); self.entries[-1][2] = Worker(manager)
        except BaseException:
            self.close(); raise

    def tick(self):
        for entry in self.entries:
            manager, lock, worker, failed = entry
            if failed: continue
            try:
                worker.tick()
                with manager.store.transaction() as c:
                    c.execute("INSERT INTO meta VALUES('connector_worker_heartbeat',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (str(time.time()),))
            except Exception:
                entry[3] = True
                print('GUI Test worker stopped scheduling; explicit restart required. BSP worker remains active.', flush=True)

    def close(self):
        for manager, lock, worker, failed in reversed(self.entries):
            if worker is not None: worker.close()
            lock.__exit__(None,None,None)
        self.entries = []
