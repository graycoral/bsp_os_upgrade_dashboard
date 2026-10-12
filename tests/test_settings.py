from copy import deepcopy
from pathlib import Path
import subprocess

import pytest

from backend.domain.engine import Engine
from backend.domain.policy import Conflict
from backend.settings import (Profile, bridge_defaults, executable_status,
                              resolve_source_revision, validate_live)
from backend.storage.store import Store


def git(folder, *args):
    return subprocess.run(['git', '-C', str(folder), *args], capture_output=True,
                          check=True, text=True).stdout.strip()


@pytest.fixture
def live_profile(tmp_path):
    source = tmp_path / 'new source'; source.mkdir()
    git(source, 'init', '-q')
    (source / 'source.txt').write_text('baseline\n')
    git(source, 'add', '.')
    git(source, '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-qm', 'baseline')
    workspace = tmp_path / 'work'; workspace.mkdir()
    profile = Profile(workspace=str(workspace), runner='bridge', **bridge_defaults(str(workspace)), execution='bridge', new_base=str(source),
                      old_base=str(source), vendor_tree=str(source)).model_dump()
    for argv in [*profile['agents'].values(), profile['build_argv']]:
        path = Path(argv[0]); path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text('#!/bin/sh\ntouch MUST_NOT_RUN\nexit 1\n'); path.chmod(0o700)
    return profile


def test_t92_auto_revision_reads_clean_head_without_mutating_profile(live_profile):
    profile = live_profile; before = deepcopy(profile)
    assert validate_live(profile) == git(profile['new_base'], 'rev-parse', 'HEAD')
    assert profile == before
    assert git(profile['new_base'], 'status', '--porcelain') == ''
    assert not (Path(profile['workspace']) / 'MUST_NOT_RUN').exists()


def test_t92_job_pins_revision_once_and_replayed_start_keeps_it(live_profile, tmp_path):
    engine = Engine(Store(tmp_path / 'db.sqlite'), tmp_path / 'artifacts')
    config = deepcopy(live_profile)
    first = engine.create('start-once', config, 'test', 'linux')
    job = engine.store.snapshot(first['job_id'])
    original = git(config['new_base'], 'rev-parse', 'HEAD')
    assert job['source_revision'] == original == job['profile']['source_revision']
    (Path(config['new_base']) / 'source.txt').write_text('next version\n')
    git(config['new_base'], 'add', '.')
    git(config['new_base'], '-c', 'user.name=Fixture', '-c', 'user.email=fixture@example.invalid', 'commit', '-qm', 'next version')
    assert engine.create('start-once', config, 'test', 'linux') == first
    assert engine.store.snapshot(first['job_id'])['source_revision'] == original
    next_job = engine.create('start-next', config, 'test', 'linux')
    assert engine.store.snapshot(next_job['job_id'])['source_revision'] != original
    assert config['source_revision'] == ''


@pytest.mark.parametrize('change', ['modified', 'untracked', 'not_git', 'no_commits'])
def test_t93_unfixed_source_does_not_start_job(live_profile, tmp_path, change):
    source = Path(live_profile['new_base'])
    if change == 'modified': (source / 'source.txt').write_text('uncommitted')
    if change == 'untracked': (source / 'new.txt').write_text('untracked')
    if change in {'not_git', 'no_commits'}:
        source = tmp_path / change; source.mkdir(); live_profile['new_base'] = str(source)
        if change == 'no_commits': git(source, 'init', '-q')
    engine = Engine(Store(tmp_path / 'db.sqlite'), tmp_path / 'artifacts')
    with pytest.raises(Conflict): engine.create('blocked', live_profile, 'test', 'linux')
    assert engine.store.all() == []


@pytest.mark.parametrize('revision', ['a' * 40, 'b' * 64])
def test_t93_manual_snapshot_identifier_is_preserved(live_profile, revision):
    live_profile['source_revision'] = revision.upper()
    assert validate_live(live_profile) == revision


@pytest.mark.parametrize('revision', ['HEAD', 'main', 'short-sha', 'a' * 41, 'demo-os-v1'])
def test_t93_manual_identifier_must_be_full_hash(live_profile, revision):
    live_profile['source_revision'] = revision
    with pytest.raises(Conflict): validate_live(live_profile)


def test_t93_source_selection_ignores_inherited_git_environment(live_profile, monkeypatch):
    monkeypatch.setenv('GIT_DIR', '/does/not/exist')
    monkeypatch.setenv('GIT_WORK_TREE', '/wrong/worktree')
    assert len(resolve_source_revision(live_profile)) == 40


def test_t93_auto_resolution_does_not_invoke_repository_fsmonitor(live_profile, tmp_path):
    marker = tmp_path / 'fsmonitor-called'
    hook = tmp_path / 'fsmonitor.sh'
    hook.write_text(f'#!/bin/sh\ntouch "{marker}"\n')
    hook.chmod(0o700)
    git(live_profile['new_base'], 'config', 'core.fsmonitor', str(hook))
    assert len(resolve_source_revision(live_profile)) == 40
    assert not marker.exists()


def test_t94_default_paths_follow_initial_workspace_and_explicit_empty_is_preserved():
    p = Profile(workspace='/srv/my bsp', runner='bridge', **bridge_defaults('/srv/my bsp')).model_dump()
    assert p['agents']['claude'] == ['/srv/my bsp/.bsp-dashboard/bridges/claude']
    assert p['build_argv'] == ['/srv/my bsp/.bsp-dashboard/bridges/build']
    custom = Profile(agents={'claude':['/custom/bridge'], 'opencode':[], 'codex':[]}, build_argv=[])
    assert custom.agents['claude'] == ['/custom/bridge'] and custom.agents['opencode'] == []
    assert custom.build_argv == []
    with pytest.raises(Conflict): bridge_defaults('relative/path')


def test_t94_bridge_probe_checks_files_without_executing(tmp_path):
    assert executable_status([])[0] == 'NOT_CONFIGURED'
    assert executable_status(['claude'])[0] == 'INVALID'
    assert executable_status([str(tmp_path / 'missing')])[0] == 'MISSING'
    assert executable_status([str(tmp_path)])[0] == 'MISSING'
    path = tmp_path / 'bridge'; path.write_text('#!/bin/sh\ntouch marker\n')
    assert executable_status([str(path)])[0] == 'NOT_EXECUTABLE'
    path.chmod(0o700)
    assert executable_status([str(path)])[0] == 'FILE_READY'
    assert not (tmp_path / 'marker').exists()


def test_t94_missing_optional_bridge_can_be_explicitly_disabled(live_profile):
    Path(live_profile['agents']['codex'][0]).unlink()
    with pytest.raises(Conflict, match='codex'): validate_live(live_profile)
    live_profile['agents']['codex'] = []
    assert validate_live(live_profile)


def test_t92_demo_needs_no_git_or_user_hash(tmp_path):
    engine = Engine(Store(tmp_path / 'db.sqlite'), tmp_path / 'artifacts')
    job = engine.create('demo', Profile().model_dump(), 'test', 'linux')
    assert engine.store.snapshot(job['job_id'])['source_revision'] == 'demo-os-v1'
