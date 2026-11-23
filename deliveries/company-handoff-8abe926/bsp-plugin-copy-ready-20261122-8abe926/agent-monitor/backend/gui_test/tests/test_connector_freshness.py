"""Registration cannot replace a fresh matching console receipt for new work."""
import json

import pytest

from backend.gui_test.connector.registry import ConnectorRegistry, RegisteredWindows
from backend.gui_test.core.models import TestError


@pytest.fixture
def connected(tmp_path):
    clock = [100.0]; calls = []; mapping = ['mapping-one']
    class Remote:
        def request(self, path):
            calls.append(path)
            if path == '/identity': return {'runner_id': 'runner', 'connector_inventory_v1': True}
            if path == '/inventory': return {'runner_id': 'runner', 'mapping_revision': mapping[0], 'boards': []}
            return {}
        def readiness(self): return {'ready': True}
        def verify(self, *args): calls.append('verify'); return True
        def boards(self): return []
        def reserve_batch(self, *args): calls.append('reserve'); return {}
        def prepare_batch(self, *args): calls.append('prepare'); return {}
        def begin_integration(self, *args): calls.append('begin'); return {}
        def execute(self, *args): calls.append('execute')
        def reconcile_integration(self, *args): calls.append('reconcile'); return {'state': 'UNKNOWN'}
        def cancel_batch(self, *args): calls.append('cancel'); return {}
        def probe(self, *args): calls.append('probe'); return 'UNKNOWN'
    registry = ConnectorRegistry(tmp_path, factory=lambda url: Remote(), clock=lambda: clock[0])
    registry.register('http://127.0.0.1:8771', 'runner')
    return registry, RegisteredWindows(registry), clock, calls, mapping


def test_registration_without_console_never_opens_execution_gate(connected):
    registry, adapter, *_ = connected
    assert registry.console()['stale'] and not adapter.readiness()['ready'] and not adapter.inventory()['fresh']
    with pytest.raises(TestError) as error: adapter.verify({}, False)
    assert error.value.code == 'CONNECTOR_STALE'


def test_refreshed_registration_does_not_refresh_failed_console_transfer(connected):
    registry, adapter, clock, calls, _ = connected
    registry.save_console({'runner_id': 'runner', 'boards': []})
    assert adapter.readiness()['ready'] and adapter.inventory()['fresh']
    clock[0] = 200
    registry.register('http://127.0.0.1:8771', 'runner')
    assert registry.console()['stale'] and not adapter.readiness()['ready'] and not adapter.inventory()['fresh']
    for operation in (lambda: adapter.verify({}, False), lambda: adapter.reserve_batch({}),
                      lambda: adapter.prepare_batch('batch', {}),
                      lambda: adapter.begin_integration({}, {'config': {'runner_id': 'runner'}}),
                      lambda: adapter.execute(None, {}, 1, {'runner_id_snapshot': 'runner'}, None, None)):
        with pytest.raises(TestError) as error: operation()
        assert error.value.code == 'CONNECTOR_STALE'
    assert not any(value in calls for value in ('verify', 'reserve', 'prepare', 'begin', 'execute'))
    assert adapter.reconcile_integration('run', {'runner_id': 'runner'}) == {'state': 'UNKNOWN'}
    adapter.cancel_batch({}); assert adapter.probe('process') == 'UNKNOWN'
    assert all(value in calls for value in ('reconcile', 'cancel', 'probe'))
    registry.save_console({'runner_id': 'runner', 'boards': []})
    assert adapter.readiness()['ready'] and adapter.verify({}, False)


def test_mapping_change_rejects_previous_console_until_matching_receipt(connected):
    registry, adapter, clock, calls, mapping = connected
    registry.save_console({'runner_id': 'runner', 'boards': []})
    mapping[0] = 'mapping-two'; clock[0] += 1
    registry.register('http://127.0.0.1:8771', 'runner')
    assert registry.console()['stale'] and not adapter.readiness()['ready']
    registry.save_console({'runner_id': 'runner', 'boards': []})
    assert adapter.readiness()['ready']


def test_delayed_console_cannot_be_relabelled_with_new_registration(connected):
    registry, adapter, clock, calls, mapping = connected
    original = registry.read()
    registry.save_console({'runner_id': 'runner', 'boards': []}, expected_registration=original)
    mapping[0] = 'mapping-two'; clock[0] += 1
    registry.register('http://127.0.0.1:8771', 'runner')
    with pytest.raises(TestError) as error:
        registry.save_console({'runner_id': 'runner', 'boards': []}, expected_registration=original)
    assert error.value.code == 'CONNECTOR_STALE' and not adapter.readiness()['ready']


@pytest.mark.parametrize('changes', [{'runner_id': 'other'}, {'received_at': 101}, {'received_at': '100'},
                                   {'received_at': True}, {'registration_revision': 'other'}])
def test_mismatched_or_invalid_projection_never_opens_gate(connected, changes):
    registry, adapter, *_ = connected
    projection = registry.save_console({'runner_id': 'runner', 'boards': []}) | changes
    with registry.connection() as c: c.execute('UPDATE console_projection SET data=? WHERE id=1', (json.dumps(projection),))
    assert not adapter.readiness()['ready'] and not adapter.inventory()['fresh']
