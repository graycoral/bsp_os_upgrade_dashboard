"""Fail closed on Git/tool failures; preserve committed subtree and exclusion rules."""
import subprocess
from pathlib import Path

import pytest

from backend.gui_test.core.models import TestError
from backend.gui_test.core.sources import SourceService
from backend.gui_test.core.store import Store
from backend.gui_test.tests.test_git_info import git_command, repository


@pytest.fixture
def service(tmp_path):
    return SourceService(Store(tmp_path / 'runtime' / 'runs.db'))


def test_dirty_subtree_uses_committed_files_then_git_failure_preserves_active(service, repository, monkeypatch):
    subtree = repository / 'TC'
    subtree.mkdir()
    (subtree / 'case.py').write_text("print('Test Result: PASS')\n")
    git_command(repository, 'add', '--', 'TC')
    git_command(repository, 'commit', '--quiet', '-m', 'Add subtree')
    (subtree / 'case.py').write_text("raise RuntimeError('dirty bytes')\n")
    (subtree / 'untracked.py').write_text('untracked')
    inspection = service.inspect('server-folder', str(subtree))
    applied = service.apply(inspection['inspection_id'], inspection['default_ref'], 0)
    assert applied['active']['commit'] == git_command(repository, 'rev-parse', 'HEAD')
    assert [tc['path'] for tc in service.catalog()['tests']] == ['case.py']
    frozen = service.directory(service.descriptor())
    assert (frozen / 'case.py').read_text() == "print('Test Result: PASS')\n"
    before = service.state()
    def unavailable(*args, **kwargs):
        raise FileNotFoundError('Git disappeared')
    monkeypatch.setattr(subprocess, 'run', unavailable)
    with pytest.raises(TestError) as failure:
        service.inspect('server-folder', str(subtree))
    assert failure.value.code == 'SOURCE_GIT_FAILED'
    assert service.state() == before
    assert (frozen / 'case.py').read_text() == "print('Test Result: PASS')\n"


@pytest.mark.parametrize('failure', ['missing', 'timeout', 'ownership', 'unknown'])
def test_git_failures_never_select_folder_semantics(service, tmp_path, monkeypatch, failure):
    root = tmp_path / 'plain'; root.mkdir()
    (root / 'case.py').write_text('print("Test Result: PASS")')
    before = service.state()
    def broken(argv, **kwargs):
        if failure == 'missing':
            raise FileNotFoundError('git')
        if failure == 'timeout':
            raise subprocess.TimeoutExpired(argv, 60)
        kwargs['stderr'].write(b'fatal: detected dubious ownership' if failure == 'ownership' else b'fatal: access failed')
        return subprocess.CompletedProcess(argv, 128)
    monkeypatch.setattr(subprocess, 'run', broken)
    with pytest.raises(TestError) as error:
        service.inspect('server-folder', str(root))
    assert error.value.code == 'SOURCE_GIT_FAILED'
    assert service.state() == before


@pytest.mark.parametrize('marker', ['ancestor', 'bare'])
def test_explicit_non_repository_with_repository_markers_still_fails(service, tmp_path, monkeypatch, marker):
    parent = tmp_path / 'damaged'; parent.mkdir()
    root = parent / 'TC'; root.mkdir()
    (parent / '.git' if marker == 'ancestor' else root / 'HEAD').write_text('broken')
    def not_repository(argv, **kwargs):
        kwargs['stderr'].write(b'fatal: not a git repository (or any of the parent directories): .git\n')
        return subprocess.CompletedProcess(argv, 128)
    monkeypatch.setattr(subprocess, 'run', not_repository)
    before = service.state()
    with pytest.raises(TestError) as error:
        service.inspect('server-folder', str(root))
    assert error.value.code == 'SOURCE_GIT_FAILED'
    assert service.state() == before


@pytest.mark.parametrize('included', [False, True])
def test_folder_links_follow_exclusion_rules(service, tmp_path, included):
    root = tmp_path / 'plain'; root.mkdir()
    (root / 'case.py').write_text('print("Test Result: PASS")')
    outside = tmp_path / 'outside.py'; outside.write_text('private bytes')
    link = root / ('linked.py' if included else '.hidden-link')
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip('OS user cannot create symbolic links')
    before = service.state()
    if included:
        with pytest.raises(TestError) as error:
            service.inspect('server-folder', str(root))
        assert error.value.code == 'SOURCE_UNSAFE'
        assert service.state() == before
    else:
        inspection = service.inspect('server-folder', str(root))
        service.apply(inspection['inspection_id'], None, before['version'])
        assert [tc['path'] for tc in service.catalog()['tests']] == ['case.py']
        assert not (service.directory(service.descriptor()) / link.name).exists()


@pytest.mark.parametrize('name,included', [('node_modules/link.py', False), ('.hidden/link.py', False), ('included.py', True)])
def test_git_links_follow_same_exclusion_rules(service, repository, name, included):
    # Git index modes exercise link rejection even when Windows cannot create symlinks.
    blob = git_command(repository, 'hash-object', '-w', '--stdin')
    git_command(repository, 'update-index', '--add', '--cacheinfo', f'120000,{blob},{name}')
    git_command(repository, 'commit', '--quiet', '-m', 'Add index link')
    inspection = service.inspect('server-folder', str(repository))
    before = service.state()
    if included:
        with pytest.raises(TestError) as error:
            service.apply(inspection['inspection_id'], inspection['default_ref'], before['version'])
        assert error.value.code == 'SOURCE_UNSAFE'
        assert service.state() == before
    else:
        service.apply(inspection['inspection_id'], inspection['default_ref'], before['version'])
        assert [tc['path'] for tc in service.catalog()['tests']] == ['case.py']
