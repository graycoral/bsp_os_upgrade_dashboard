"""Read-only TC Git observations, isolation and snapshot compatibility; no network."""
from datetime import datetime
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory

import pytest

from backend.gui_test.adapters.windows_remote import WindowsRemote
from backend.gui_test.core.manager import Manager
from backend.gui_test.core.store import Store
from backend.gui_test.execution import git_info
from backend.gui_test.execution.host import Host


def git_command(repo, *args):
    executable = shutil.which('git')
    if not executable:
        pytest.skip('A local Git executable is required for repository fixtures')
    env = {key: value for key, value in os.environ.items() if not key.upper().startswith('GIT_')}
    env.update(GIT_CONFIG_NOSYSTEM='1', GIT_CONFIG_GLOBAL=os.devnull, GIT_TERMINAL_PROMPT='0')
    result = subprocess.run(
        [executable, '-C', str(repo), '-c', 'user.name=Git Metadata Fixture',
         '-c', 'user.email=git-fixture@example.invalid', '-c', 'commit.gpgsign=false', *args],
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        check=True, timeout=10, env=env, shell=False)
    return result.stdout.decode('utf-8').strip()


@pytest.fixture
def repository(tmp_path):
    root = tmp_path / 'TC source 한글'
    root.mkdir()
    # No init -b assumption: deployed Windows Git can predate that option.
    git_command(root, 'init', '--quiet')
    git_command(root, 'symbolic-ref', 'HEAD', 'refs/heads/fixture-main')
    (root / 'case.py').write_text("print('Test Result: PASS')\n", encoding='utf-8')
    git_command(root, 'add', '--', 'case.py')
    git_command(root, 'commit', '--quiet', '-m', 'Initial fixture')
    return root


def test_local_repository_observes_full_head_without_changing_files_or_index(repository):
    git_command(repository, 'config', 'remote.origin.url', 'https://fixture-user:fixture-secret@example.invalid/tc.git?token=fixture-secret#fragment')
    nested = repository / 'nested cases'
    nested.mkdir()
    (repository / 'case.py').write_text("print('uncommitted fixture')\n", encoding='utf-8')
    before = git_command(repository, 'status', '--porcelain')
    index_before = (repository / '.git' / 'index').read_bytes()
    expected = git_command(repository, 'rev-parse', 'HEAD')

    value = git_info.inspect_git(nested)

    assert value['status'] == 'available'
    assert Path(value['source_path']) == nested.resolve()
    assert Path(value['repository_path']) == repository.resolve()
    assert value['branch'] == 'fixture-main' and value['detached'] is False
    assert value['commit'] == expected and len(value['commit']) == 40
    assert value['remote'] == 'https://example.invalid/tc.git'
    assert datetime.fromisoformat(value['checked_at']).utcoffset() is not None
    assert 'fixture-secret' not in json.dumps(value)
    assert git_command(repository, 'status', '--porcelain') == before
    assert (repository / '.git' / 'index').read_bytes() == index_before
    assert (repository / 'case.py').read_text(encoding='utf-8') == "print('uncommitted fixture')\n"


def test_detached_head_does_not_invent_a_branch(repository):
    commit = git_command(repository, 'rev-parse', 'HEAD')
    git_command(repository, 'checkout', '--quiet', '--detach', commit)
    value = git_info.inspect_git(repository)
    assert value['status'] == 'available'
    assert value['detached'] is True and value['branch'] is None
    assert value['commit'] == commit and value['remote'] is None


def test_unborn_repository_reports_branch_without_a_commit(tmp_path):
    git_command(tmp_path, 'init', '--quiet')
    git_command(tmp_path, 'symbolic-ref', 'HEAD', 'refs/heads/not-yet-committed')
    value = git_info.inspect_git(tmp_path)
    assert value['status'] == 'unborn'
    assert value['branch'] == 'not-yet-committed' and value['detached'] is False
    assert value['commit'] is None and value['remote'] is None


def test_non_repository_never_reuses_the_dashboard_repository():
    if not shutil.which('git'):
        pytest.skip('A local Git executable is required to classify a non-repository')
    # --basetemp can live under the dashboard checkout, where Git correctly
    # discovers that parent repository. This negative source must be external.
    with TemporaryDirectory(prefix='tc-git-nonrepo-') as directory:
        root = Path(directory).resolve()
        assert not any((parent / '.git').exists() for parent in (root, *root.parents)), 'Negative Git fixture must be outside every repository'
        value = git_info.inspect_git(root)
        assert value['status'] == 'not_repository'
        assert value['source_path'] == str(root)
        assert value['repository_path'] is None and value['commit'] is None


@pytest.mark.parametrize('source', ['missing', 'plain-file'])
def test_missing_or_non_directory_source_returns_an_explicit_error(tmp_path, source):
    path = tmp_path / source
    if source == 'plain-file':
        path.write_text('fixture', encoding='utf-8')
    value = git_info.inspect_git(path)
    assert value['status'] == 'error'
    assert value['repository_path'] is None and value['commit'] is None


def test_inherited_git_redirects_and_config_injection_cannot_select_another_repository(repository, tmp_path, monkeypatch):
    expected = git_command(repository, 'rev-parse', 'HEAD')
    unrelated = tmp_path / 'unrelated'
    unrelated.mkdir()
    git_command(unrelated, 'init', '--quiet')
    monkeypatch.setenv('GIT_DIR', str(unrelated / '.git'))
    monkeypatch.setenv('GIT_WORK_TREE', str(unrelated))
    monkeypatch.setenv('GIT_INDEX_FILE', str(tmp_path / 'foreign-index'))
    monkeypatch.setenv('GIT_CONFIG_COUNT', '1')
    monkeypatch.setenv('GIT_CONFIG_KEY_0', 'remote.origin.url')
    monkeypatch.setenv('GIT_CONFIG_VALUE_0', 'https://fixture-secret@example.invalid/injected.git')
    value = git_info.inspect_git(repository)
    assert value['status'] == 'available' and value['commit'] == expected
    assert Path(value['repository_path']) == repository.resolve()
    assert value['remote'] is None
    assert not (tmp_path / 'foreign-index').exists()


@pytest.mark.parametrize('raw,expected', [
    ('https://name:fixture-password@example.invalid/team/tc.git?token=fixture-token#fragment', 'https://example.invalid/team/tc.git'),
    ('ssh://git:fixture-password@example.invalid:2222/team/tc.git', 'ssh://example.invalid:2222/team/tc.git'),
    ('ssh://git@[2001:db8::1]:2222/team/tc.git?key=fixture', 'ssh://[2001:db8::1]:2222/team/tc.git'),
    ('git@example.invalid:team/tc.git?token=fixture#fragment', 'example.invalid:team/tc.git'),
    ('git://example.invalid/team/tc.git', 'git://example.invalid/team/tc.git'),
    ('file:///fixtures/tc.git?key=fixture#fragment', 'file:///fixtures/tc.git'),
    ('ext::arbitrary-helper', None), ('javascript://example.invalid/arbitrary', None),
    ('https://example.invalid:invalid/tc.git', None),
    ('https://example.invalid/tc.git\nAuthorization: fixture', None),
    ('https://example.invalid/\x7ftc.git', None),
    ('/private/local/path', None), ('C:\\private\\local\\path', None),
    ('x' * 4097, None), ('', None),
])
def test_origin_redaction_only_returns_supported_locations(raw, expected):
    assert git_info._remote(raw) == expected


def test_git_missing_returns_status_without_exception_details(tmp_path, monkeypatch):
    monkeypatch.setattr(git_info.shutil, 'which', lambda *args, **kwargs: None)
    value = git_info.inspect_git(tmp_path)
    assert value['status'] == 'git_unavailable'
    assert value['remote'] is None and value['commit'] is None


class FakeGitProcess:
    def __init__(self, stdout=b'', stderr=b'', timeout=False):
        self.stdout, self.stderr = io.BytesIO(stdout), io.BytesIO(stderr)
        self.returncode = 0
        self.timeout = timeout
        self.killed = False
        self.waits = []

    def wait(self, timeout):
        self.waits.append(timeout)
        if self.timeout and not self.killed:
            raise subprocess.TimeoutExpired('git fixture', timeout)
        return self.returncode

    def kill(self):
        self.killed = True
        self.returncode = -1


@pytest.mark.parametrize('stdout_bytes,stderr_bytes,allowed', [(4096, 4096, True), (4097, 4096, False), (0, 8193, False)])
def test_bounded_git_reader_limits_combined_stdout_and_stderr(tmp_path, monkeypatch, stdout_bytes, stderr_bytes, allowed):
    process = FakeGitProcess(b'a' * stdout_bytes, b'b' * stderr_bytes)
    monkeypatch.setattr(git_info.subprocess, 'Popen', lambda *args, **kwargs: process)
    if allowed:
        code, stdout, stderr = git_info._run_git('git', tmp_path, ['fixture'], git_info.time.monotonic() + 2, {})
        assert code == 0 and len(stdout.encode()) + len(stderr.encode()) == 8192
        assert not process.killed
    else:
        with pytest.raises(git_info._GitReadError) as raised:
            git_info._run_git('git', tmp_path, ['fixture'], git_info.time.monotonic() + 2, {})
        assert raised.value.status == 'error' and process.killed


def test_timeout_kills_the_child_and_returns_timeout_not_git_output(tmp_path, monkeypatch):
    process = FakeGitProcess(stderr=b'private fixture error', timeout=True)
    monkeypatch.setattr(git_info.subprocess, 'Popen', lambda *args, **kwargs: process)
    with pytest.raises(git_info._GitReadError) as raised:
        git_info._run_git('git', tmp_path, ['fixture'], git_info.time.monotonic() + 2, {})
    assert raised.value.status == 'timeout' and process.killed
    assert 0 < process.waits[0] <= 2
    assert process.waits[1] == 0.1


def test_expired_total_deadline_does_not_launch_another_git_process(tmp_path, monkeypatch):
    def forbidden(*args, **kwargs):
        pytest.fail('An expired metadata request must not launch a Git process')
    monkeypatch.setattr(git_info.subprocess, 'Popen', forbidden)
    with pytest.raises(git_info._GitReadError) as raised:
        git_info._run_git('git', tmp_path, ['fixture'], git_info.time.monotonic() - 1, {})
    assert raised.value.status == 'timeout'


def test_all_git_commands_share_one_two_second_deadline(tmp_path, monkeypatch):
    calls = []
    monkeypatch.setattr(git_info.shutil, 'which', lambda *args, **kwargs: 'git-fixture')

    def read(executable, root, args, deadline, env):
        calls.append((args, deadline, env))
        if args[0] == 'rev-parse' and '--show-toplevel' in args:
            return 0, str(tmp_path.resolve()), ''
        if args[0] == 'symbolic-ref':
            return 0, 'fixture-main', ''
        if args[0] == 'rev-parse':
            return 0, 'a' * 40, ''
        raise git_info._GitReadError('timeout')

    monkeypatch.setattr(git_info, '_run_git', read)
    before = git_info.time.monotonic()
    value = git_info.inspect_git(tmp_path)
    assert value['status'] == 'timeout'
    assert len(calls) == 4 and len({call[1] for call in calls}) == 1
    assert before + 1.9 < calls[0][1] <= git_info.time.monotonic() + 2
    env = calls[0][2]
    assert env['GIT_TERMINAL_PROMPT'] == '0' and env['GIT_OPTIONAL_LOCKS'] == '0'


@pytest.mark.parametrize('failure,status', [(FileNotFoundError('private fixture path'), 'git_unavailable'), (PermissionError('private fixture path'), 'error')])
def test_process_launch_failures_map_to_public_status(tmp_path, monkeypatch, failure, status):
    monkeypatch.setattr(git_info.shutil, 'which', lambda *args, **kwargs: 'git-fixture')
    def fail(*args, **kwargs):
        raise failure
    monkeypatch.setattr(git_info.subprocess, 'Popen', fail)
    value = git_info.inspect_git(tmp_path)
    assert value['status'] == status
    assert 'private fixture path' not in json.dumps(value)


def test_host_git_metadata_cannot_replace_or_change_the_executable_snapshot_revision(repository, tmp_path):
    host = Host({'source_root': str(repository), 'python': sys.executable,
                 'boards': [{'host': 'fixture-windows', 'board_id': 'fixture-a', 'com': 'COM31'}]},
                tmp_path / 'runner-runtime', ports=lambda: {'COM31'})
    first = host.catalog()
    assert first['git']['status'] == 'available'
    assert first['revision'].startswith('shared-') and first['revision'] != first['git']['commit']
    git_command(repository, 'commit', '--allow-empty', '--quiet', '-m', 'Metadata-only commit')
    git_command(repository, 'config', 'remote.origin.url', 'https://example.invalid/another.git')
    second = host.catalog()
    assert second['git']['commit'] != first['git']['commit']
    assert second['revision'] == first['revision'] and second['tests'] == first['tests']
    (repository / 'case.py').write_text("print('Test Result: FAIL')\n", encoding='utf-8')
    third = host.catalog()
    assert third['git']['commit'] == second['git']['commit']
    assert third['revision'] != second['revision']


@pytest.mark.parametrize('with_git', [False, True])
def test_runner_catalog_remains_compatible_when_optional_git_is_absent_or_present(tmp_path, monkeypatch, with_git):
    old_catalog = {'branch': 'shared', 'revision': 'shared-fixture', 'metadata_revision': 'metadata-fixture', 'tests': []}
    if with_git:
        old_catalog['git'] = {'status': 'available', 'commit': 'a' * 40}
    remote = WindowsRemote('http://localhost', 'fixture-' + 'x' * 32, client=object())
    calls = []
    def request(path, *args, **kwargs):
        calls.append(path)
        assert path == '/catalog'
        return old_catalog.copy()
    monkeypatch.setattr(remote, 'request', request)
    manager = Manager(Store(tmp_path / 'runs.db'), mode='dashboard', adapter=remote)
    value = manager.catalog('shared')
    assert value == old_catalog | {'timeout_settings_revision': manager.timeouts.read()['revision'], 'timeout_settings_active': False}
    assert ('git' in value) is with_git
    assert calls == ['/catalog']
