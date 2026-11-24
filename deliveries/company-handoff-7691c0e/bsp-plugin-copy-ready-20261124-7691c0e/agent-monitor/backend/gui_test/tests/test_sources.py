"""Registered TC source behavior using local bytes and local Git; no remote or TC execution."""
from pathlib import Path

import pytest

from backend.gui_test.core.models import TestError
from backend.gui_test.core.sources import SourceService
from backend.gui_test.core.store import Store
from .test_git_info import git_command, repository


@pytest.fixture
def service(tmp_path):
    return SourceService(Store(tmp_path / 'state' / 'runs.db'))


@pytest.fixture
def folder(tmp_path):
    root = tmp_path / 'TC source 한글'
    root.mkdir()
    (root / 'case.py').write_text("print('Test Result: PASS')\n", encoding='utf-8')
    (root / 'support').mkdir()
    (root / 'support' / 'payload.bin').write_bytes(b'\x00\xfforiginal dependency\r\n')
    return root


def register(service, root, ref=None):
    inspection = service.inspect('server-folder', str(root))
    result = service.apply(inspection['inspection_id'], ref, service.state()['version'])
    return inspection, result


def test_folder_registration_materializes_auxiliary_bytes_and_keeps_original_unchanged(service, folder):
    """T-176: a catalog is bound to immutable full source bytes, not just .py names."""
    initial = service.state()
    assert initial['active']['kind'] == 'legacy'
    inspection, applied = register(service, folder)
    assert inspection['refs'] == [] and inspection['default_ref'] is None
    assert applied['version'] > initial['version']
    assert applied['active']['kind'] == 'server-folder'
    assert applied['active']['ref'] is None and applied['active']['commit'] is None
    assert [tc['path'] for tc in applied['catalog']['tests']] == ['case.py']
    descriptor = service.descriptor()
    snapshot = Path(service.directory(descriptor))
    assert snapshot.resolve() != folder.resolve()
    assert (snapshot / 'support' / 'payload.bin').read_bytes() == b'\x00\xfforiginal dependency\r\n'
    original_revision = applied['catalog']['revision']
    (folder / 'case.py').write_text("raise RuntimeError('changed after apply')\n", encoding='utf-8')
    (folder / 'support' / 'payload.bin').write_bytes(b'changed original')
    assert service.catalog()['revision'] == original_revision
    assert (snapshot / 'case.py').read_text(encoding='utf-8') == "print('Test Result: PASS')\n"
    assert (snapshot / 'support' / 'payload.bin').read_bytes() == b'\x00\xfforiginal dependency\r\n'
    assert (folder / 'support' / 'payload.bin').read_bytes() == b'changed original'


def test_long_runtime_path_registration_remains_readable_transportable_and_copyable(tmp_path, folder):
    """T-177/T-178 / REG0064: successful apply must survive final paths beyond MAX_PATH."""
    import os
    from backend.gui_test.execution import source_snapshots as snapshots

    runtime = tmp_path / 'long-source-runtime'
    while len(str(runtime.resolve())) < 230:
        runtime /= 'nested-runtime-segment'
    original_case_bytes = (folder / 'case.py').read_bytes()
    service = SourceService(Store(tmp_path / 'state' / 'runs.db'), runtime=runtime)
    _, applied = register(service, folder)
    descriptor = service.descriptor()
    snapshot = service.directory(descriptor)
    assert len(str(snapshot / snapshots.MANIFEST)) >= 300
    # Final publication renames a shorter staging directory to a 64-character
    # ID. An HTTP 200 alone does not prove the manifest remains accessible at
    # that longer final path, so exercise each subsequent public operation.
    assert service.catalog()['revision'] == applied['catalog']['revision']
    reopened = SourceService(Store(service.store.path), runtime=runtime)
    assert reopened.state() == service.state()
    assert reopened.catalog()['revision'] == applied['catalog']['revision']
    archive = tmp_path / 'long-runtime-source.zip'
    with snapshots.create_archive(reopened.directory(descriptor), descriptor) as stream:
        archive.write_bytes(stream.read())
    received = runtime / 'received'
    snapshots.receive_archive(archive, descriptor['snapshot_id'], received)
    attempt = runtime / 'attempts' / 'attempt-one'
    catalog = snapshots.copy_snapshot(received / descriptor['snapshot_id'], attempt, descriptor['source_revision'])
    assert catalog['revision'] == applied['catalog']['revision']
    assert [tc['path'] for tc in catalog['tests']] == ['case.py']

    def contents(path):
        # Verify filesystem bytes independently of the product's path helper;
        # ordinary pathlib on Windows may itself impose the legacy path limit.
        path = path.resolve()
        if os.name == 'nt' and not str(path).startswith('\\\\?\\'):
            path = Path('\\\\?\\' + str(path))
        return path.read_bytes()

    assert contents(attempt / 'case.py') == original_case_bytes
    assert contents(attempt / 'support' / 'payload.bin') == b'\x00\xfforiginal dependency\r\n'
    assert (folder / 'support' / 'payload.bin').read_bytes() == b'\x00\xfforiginal dependency\r\n'


def test_local_git_refs_use_committed_trees_without_checkout_or_worktree_changes(service, repository):
    """T-176: select a different branch while preserving dirty files, index and HEAD."""
    main = git_command(repository, 'rev-parse', 'HEAD')
    git_command(repository, 'checkout', '--quiet', '-b', 'fixture-feature')
    (repository / 'feature.py').write_text("print('feature')\n", encoding='utf-8')
    (repository / 'helper.txt').write_text('feature auxiliary', encoding='utf-8')
    git_command(repository, 'add', '--', 'feature.py', 'helper.txt')
    git_command(repository, 'commit', '--quiet', '-m', 'Feature source')
    feature = git_command(repository, 'rev-parse', 'HEAD')
    git_command(repository, 'checkout', '--quiet', 'fixture-main')
    (repository / 'case.py').write_text('dirty original\n', encoding='utf-8')
    before_status = git_command(repository, 'status', '--porcelain')
    before_index = (repository / '.git' / 'index').read_bytes()
    inspection = service.inspect('server-folder', str(repository))
    refs = {item['ref']: item['commit'] for item in inspection['refs']}
    assert refs['refs/heads/fixture-main'] == main
    assert refs['refs/heads/fixture-feature'] == feature
    applied = service.apply(inspection['inspection_id'], 'refs/heads/fixture-feature', service.state()['version'])
    assert applied['active']['commit'] == feature
    assert {tc['path'] for tc in applied['catalog']['tests']} == {'case.py', 'feature.py'}
    snapshot = Path(service.directory(service.descriptor()))
    assert (snapshot / 'helper.txt').read_text(encoding='utf-8') == 'feature auxiliary'
    assert (snapshot / 'case.py').read_text(encoding='utf-8') == "print('Test Result: PASS')\n"
    assert git_command(repository, 'rev-parse', 'HEAD') == main
    assert git_command(repository, 'status', '--porcelain') == before_status
    assert (repository / '.git' / 'index').read_bytes() == before_index
    assert (repository / 'case.py').read_text(encoding='utf-8') == 'dirty original\n'


def test_git_tc_subfolder_uses_repository_refs_and_committed_relative_subtree(service, repository):
    """T-176: a TC subfolder excludes unrelated repository paths and dirty bytes."""
    source = repository / 'project' / 'test cases'
    source.mkdir(parents=True)
    (source / 'subcase.py').write_text("print('committed subtree')\n", encoding='utf-8')
    (source / 'input.txt').write_text('committed auxiliary', encoding='utf-8')
    git_command(repository, 'add', '--', 'project')
    git_command(repository, 'commit', '--quiet', '-m', 'Add TC subtree')
    head = git_command(repository, 'rev-parse', 'HEAD')
    (source / 'subcase.py').write_text('dirty subtree\n', encoding='utf-8')
    before = git_command(repository, 'status', '--porcelain')
    inspection = service.inspect('server-folder', str(source))
    assert {row['ref'] for row in inspection['refs']} == {'refs/heads/fixture-main'}
    assert inspection['refs'][0]['commit'] == head
    applied = service.apply(inspection['inspection_id'], 'refs/heads/fixture-main', service.state()['version'])
    assert [row['path'] for row in applied['catalog']['tests']] == ['subcase.py']
    snapshot = service.directory(service.descriptor())
    assert (snapshot / 'input.txt').read_text(encoding='utf-8') == 'committed auxiliary'
    assert (snapshot / 'subcase.py').read_text(encoding='utf-8') == "print('committed subtree')\n"
    assert not (snapshot / 'case.py').exists()
    assert git_command(repository, 'rev-parse', 'HEAD') == head
    assert git_command(repository, 'status', '--porcelain') == before


def test_same_bytes_new_source_and_new_generation_do_not_reuse_catalog_identity(service, folder, tmp_path):
    """T-177: source identity/generation invalidates old selection even with identical TC text."""
    import shutil
    _, first = register(service, folder)
    other = tmp_path / 'different source'
    shutil.copytree(folder, other)
    _, second = register(service, other)
    _, third = register(service, other)
    assert len({first['catalog']['revision'], second['catalog']['revision'], third['catalog']['revision']}) == 3
    assert first['catalog']['tests'][0]['content_hash'] == second['catalog']['tests'][0]['content_hash']
    assert first['active']['location'] != second['active']['location']
    assert first['version'] < second['version'] < third['version']


def test_compare_and_swap_rejects_stale_apply_without_changing_active_and_survives_restart(service, folder):
    """T-177: persistent source version is shared across service instances."""
    inspection = service.inspect('server-folder', str(folder))
    version = service.state()['version']
    other = SourceService(Store(service.store.path))
    applied = other.apply(inspection['inspection_id'], None, version)
    with pytest.raises(TestError) as stale:
        service.apply(inspection['inspection_id'], None, version)
    assert stale.value.status == 409
    reopened = SourceService(Store(service.store.path))
    assert reopened.state() == other.state()
    assert reopened.state()['active'] == applied['active']
    assert reopened.catalog()['revision'] == applied['catalog']['revision']


def test_failed_inspect_unknown_ref_and_missing_source_preserve_active(service, folder):
    """T-177: inspection/apply failures cannot erase the last usable catalog."""
    _, applied = register(service, folder)
    before = service.state()
    with pytest.raises(TestError):
        service.inspect('server-folder', str(folder / 'missing'))
    inspection = service.inspect('server-folder', str(folder))
    with pytest.raises(TestError):
        service.apply(inspection['inspection_id'], 'refs/heads/not-inspected', before['version'])
    with pytest.raises(TestError):
        service.apply('missing-inspection', None, before['version'])
    assert service.state() == before
    assert service.catalog()['revision'] == applied['catalog']['revision']


def test_explicit_legacy_revert_advances_version_and_keeps_previous_frozen_snapshot(service, folder):
    """T-177: returning to defaults is explicit and does not delete frozen Run inputs."""
    _, selected = register(service, folder)
    previous = service.descriptor()
    inspection = service.inspect('legacy', '')
    assert inspection['refs'] == [] and inspection['repository'] is False
    reverted = service.apply(inspection['inspection_id'], None, selected['version'])
    assert reverted['active']['kind'] == 'legacy'
    assert reverted['version'] > selected['version']
    assert service.descriptor() is None and service.catalog() is None
    assert (service.directory(previous) / 'case.py').read_text(encoding='utf-8') == "print('Test Result: PASS')\n"
    reopened = SourceService(Store(service.store.path))
    assert reopened.state() == service.state()


@pytest.mark.parametrize('location', ['https://user:secret@example.invalid/tc.git',
    'https://example.invalid/tc.git?token=secret', '-oProxyCommand=unsafe', 'file:///tmp/tc.git'])
def test_git_url_rejects_credentials_and_non_remote_or_option_inputs_without_network(service, location):
    """T-177: malformed/credential-bearing configuration never becomes persisted active state."""
    before = service.state()
    with pytest.raises(TestError):
        service.inspect('git-url', location)
    assert service.state() == before


@pytest.mark.parametrize('branch_moves', [False, True])
def test_remote_inspect_and_fetch_use_advertised_commit_and_reject_moving_branch(service, repository, monkeypatch, branch_moves):
    """T-176/177: mock the remote boundary, materialize fetched local Git objects."""
    advertised = git_command(repository, 'rev-parse', 'HEAD')
    remote = 'https://git.example.invalid/team/tc.git'
    actual_git = SourceService.git
    calls = []

    def git(root, *args):
        calls.append(args)
        if args[0] == 'ls-remote':
            return (f'ref: refs/heads/fixture-main\tHEAD\n' if '--symref' in args else
                    f'{advertised}\trefs/heads/fixture-main\n').encode()
        if args[0] == 'fetch':
            assert args[-2] == remote
            # This mock redirects HTTPS to a disposable local repository. The
            # production Git runner correctly denies file transport; opt in
            # only for this explicitly local test fetch, after its defaults.
            args = ('-c', 'protocol.file.allow=always', *args[:-2], str(repository), args[-1])
        return actual_git(root, *args)

    monkeypatch.setattr(service, 'git', git)
    inspection = service.inspect('git-url', remote)
    assert inspection['refs'] == [{'name': 'fixture-main', 'ref': 'refs/heads/fixture-main', 'commit': advertised}]
    before = service.state()
    if branch_moves:
        (repository / 'case.py').write_text("print('new committed source')\n", encoding='utf-8')
        git_command(repository, 'add', '--', 'case.py')
        git_command(repository, 'commit', '--quiet', '-m', 'Move branch after inspect')
        with pytest.raises(TestError) as changed:
            service.apply(inspection['inspection_id'], inspection['default_ref'], before['version'])
        assert changed.value.code == 'SOURCE_CHANGED'
        assert service.state() == before
    else:
        applied = service.apply(inspection['inspection_id'], inspection['default_ref'], before['version'])
        assert applied['active']['commit'] == advertised
        assert (service.directory(service.descriptor()) / 'case.py').read_text(encoding='utf-8') == "print('Test Result: PASS')\n"
    assert any(args[0] == 'fetch' for args in calls)
    assert not any(args[0] in {'checkout', 'switch', 'reset'} for args in calls)


def test_source_change_rejects_old_suite_and_stale_preflight_before_run_creation(tmp_path, folder, monkeypatch):
    """T-177: a previously valid selection cannot start after source generation changes."""
    from backend.gui_test.runtime import make_manager
    from backend.gui_test.core.models import uid
    from .test_core import request
    manager = make_manager(tmp_path / 'manager', 'standalone')
    register(manager.sources, folder)
    original = request(manager)
    checked = manager.preflight(original)
    suite = manager.save_document('suite', 'source suite', {'tc_ids': original['tc_ids'], 'source_revision': original['source_revision']})
    register(manager.sources, folder)
    with pytest.raises(TestError) as stale_source:
        manager.preflight(original)
    assert stale_source.value.code == 'SOURCE_CHANGED'
    with pytest.raises(TestError) as stale_suite:
        manager.preflight({**request(manager), 'suite_revision': suite['revision']})
    assert stale_suite.value.code == 'SUITE_CHANGED'
    # Simulate a source update at the boundary after validation, while the
    # manager is about to commit a Run using that completed validation.
    monkeypatch.setattr(manager, 'preflight', lambda _request: checked)
    with pytest.raises(TestError) as stale_commit:
        manager.start(uid(), 'owner', original)
    assert stale_commit.value.code == 'SOURCE_CHANGED'
    assert manager.store.all() == []


def test_existing_run_and_attempt_keep_frozen_source_when_active_registration_changes(tmp_path, folder):
    """T-179: a later source selection affects future Runs, preserving existing Run inputs."""
    from backend.gui_test.runtime import make_manager
    from backend.gui_test.core.models import uid
    from .test_core import request
    manager = make_manager(tmp_path / 'manager', 'standalone')
    _, first = register(manager.sources, folder)
    run = manager.start(uid(), 'owner', request(manager))
    assert set(run['source_snapshot']) == {'version', 'snapshot_id', 'source_revision'}
    assert run['source_snapshot']['snapshot_id'] == first['active']['snapshot_id']
    (folder / 'case.py').write_text("print('new registered bytes')\n", encoding='utf-8')
    _, second = register(manager.sources, folder)
    assert second['active']['source_revision'] != run['source_revision']
    claim = manager.claim(run['id'])
    assert claim is not None
    assert claim['context']['source_snapshot'] == run['source_snapshot']
    frozen = Path(claim['context']['source_directory'])
    assert (frozen / 'case.py').read_text(encoding='utf-8') == "print('Test Result: PASS')\n"
    assert manager.get(run['id'])['source_revision'] == first['active']['source_revision']
    assert manager.catalog()['revision'] == second['active']['source_revision']


@pytest.mark.parametrize('live', [False, True])
def test_source_api_normal_and_live_share_contract_and_keep_catalog_available_offline(tmp_path, folder, live):
    """T-179: API source editing is available without an execution-ready Windows host."""
    from fastapi.testclient import TestClient
    from backend.api.main import create_app
    app = create_app(tmp_path / 'dashboard')
    base = '/api/v1/gui-test' + ('/live' if live else '')
    with TestClient(app, client=('127.0.0.1', 1000), headers={'X-BSP-Client': 'dashboard'}) as client:
        initial = client.get(base + '/source')
        assert initial.status_code == 200
        inspection = client.post(base + '/source/inspect', json={'kind': 'server-folder', 'location': str(folder)})
        assert inspection.status_code == 200
        applied = client.put(base + '/source', json={'inspection_id': inspection.json()['inspection_id'],
                                                    'ref': None, 'expected_version': initial.json()['version']})
        assert applied.status_code == 200
        value = applied.json()
        assert value['catalog']['tests'][0]['path'] == 'case.py'
        assert client.get(base + '/catalog').json()['revision'] == value['active']['source_revision']
        if live:
            assert value['execution']['ready'] is False
            assert value['execution']['code'] == 'RUNNER_UNAVAILABLE'
        else:
            assert value['execution']['ready'] is True
        rejected = client.put(base + '/source', json={'inspection_id': inspection.json()['inspection_id'],
                                                     'ref': None, 'expected_version': initial.json()['version']})
        assert rejected.status_code == 409
        assert client.get(base + '/source').json()['active'] == value['active']
