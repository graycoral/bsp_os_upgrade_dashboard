"""Permission failures preserve UNKNOWN instead of escaping the execution thread."""
import errno
from types import SimpleNamespace
import pytest
from backend.gui_test.execution.process import ProcessTree

@pytest.mark.parametrize('number',[errno.EPERM,errno.EACCES])
def test_unreadable_process_group_is_not_termination_evidence(monkeypatch,number):
    tree=ProcessTree.__new__(ProcessTree)
    tree.job=None
    tree.process=SimpleNamespace(pid=123456,returncode=0,poll=lambda:0)
    def denied(*args): raise OSError(number,'fixture denied')
    monkeypatch.setattr('backend.gui_test.execution.process.os.killpg',denied,raising=False)
    assert tree.stopped() is False
    assert tree.stop() is False
