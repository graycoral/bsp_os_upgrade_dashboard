"""REG-0036: real Windows shell launch under a restricted inherited policy."""
import json
import os
from pathlib import Path
import subprocess
import shutil
import sys

import pytest


@pytest.fixture
def bash_build(tmp_path):
    root = Path(__file__).resolve().parents[1]
    project = tmp_path / 'project with spaces'
    scripts = project / 'scripts'
    scripts.mkdir(parents=True)
    shutil.copyfile(root / 'scripts/build-ui.sh', scripts / 'build-ui.sh')
    binaries = tmp_path / 'bin'
    binaries.mkdir()
    (binaries / 'dirname').symlink_to(shutil.which('dirname'))
    fake = '''import json, os, sys, time
from pathlib import Path
name = Path(sys.argv[0]).name
args = sys.argv[1:]
with open(os.environ['BUILD_CAPTURE'], 'a') as log:
    log.write(json.dumps({'tool': name, 'args': args, 'cwd': os.getcwd()}) + '\\n')
if args == ['--version']:
    print('v22.23.4' if name == 'node' else '10.9.4')
elif args[0] == 'ci':
    time.sleep(float(os.environ.get('BUILD_INSTALL_DELAY', '0')))
    sys.exit(int(os.environ.get('BUILD_INSTALL_EXIT', '0')))
elif args[:2] == ['run', 'build']:
    sys.exit(int(os.environ.get('BUILD_COMPILE_EXIT', '0')))
'''
    for name in ('node', 'npm'):
        path = binaries / name
        path.write_text('#!' + sys.executable + '\n' + fake)
        path.chmod(0o700)
    env = {**os.environ, 'PATH': str(binaries), 'BUILD_CAPTURE': str(tmp_path / 'calls.jsonl')}
    return [shutil.which('bash'), str(scripts / 'build-ui.sh')], env, project


@pytest.mark.skipif(os.name == 'nt', reason='POSIX Bash entrypoint')
@pytest.mark.parametrize('target,apps', [
    ('all', ['apps/web', 'apps/gui-test']),
    ('dashboard', ['apps/web']),
    ('gui-test', ['apps/gui-test']),
])
@pytest.mark.parametrize('skip_install', [False, True])
def test_t126_bash_build_stages_and_targets(bash_build, target, apps, skip_install):
    argv, env, project = bash_build
    result = subprocess.run(argv + [target] + (['--skip-install'] if skip_install else []),
                            env=env, capture_output=True, text=True, timeout=10)
    assert result.returncode == 0, result.stderr
    calls = [json.loads(line) for line in Path(env['BUILD_CAPTURE']).read_text().splitlines()]
    installs = [call for call in calls if call['args'][0] == 'ci']
    builds = [call for call in calls if call['args'][:2] == ['run', 'build']]
    assert [call['args'][3] for call in builds] == apps
    assert len(installs) == (0 if skip_install else len(apps))
    for call in installs:
        assert '--loglevel=info' in call['args'] and '--foreground-scripts' in call['args']
    assert all(Path(call['cwd']) == project for call in installs + builds)
    assert '[build-ui] Starting' in result.stdout
    assert all(f'[build-ui] Finished {app}.' in result.stdout for app in apps)


@pytest.mark.skipif(os.name == 'nt', reason='POSIX Bash entrypoint')
@pytest.mark.parametrize('variable,code,stage', [
    ('BUILD_INSTALL_EXIT', 7, 'installing dependencies'),
    ('BUILD_COMPILE_EXIT', 8, 'building'),
])
def test_t126_bash_build_failure_reports_stage(bash_build, variable, code, stage):
    argv, env, _ = bash_build
    result = subprocess.run(argv, env={**env, variable: str(code)}, capture_output=True, text=True, timeout=10)
    assert result.returncode == code
    assert f'Failed while {stage}' in result.stderr
    assert 'Finished' not in result.stdout
    assert 'apps/gui-test' not in result.stdout


@pytest.mark.skipif(os.name == 'nt', reason='POSIX Bash entrypoint')
def test_t126_bash_reports_stage_before_quiet_install(bash_build):
    argv, env, _ = bash_build
    with subprocess.Popen(argv + ['dashboard'], env={**env, 'BUILD_INSTALL_DELAY': '1'},
                          stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) as process:
        lines = []
        while 'Installing dependencies' not in ''.join(lines):
            line = process.stdout.readline()
            assert line, process.stderr.read()
            lines.append(line)
        assert process.poll() is None
        output, errors = process.communicate(timeout=10)
        assert process.returncode == 0, errors
        assert 'Finished apps/web' in output


@pytest.mark.skipif(os.name == 'nt', reason='POSIX Bash entrypoint')
@pytest.mark.parametrize('tool', ['node', 'npm'])
def test_t126_bash_missing_tool_is_actionable(bash_build, tool):
    argv, env, _ = bash_build
    (Path(env['PATH']) / tool).unlink()
    result = subprocess.run(argv, env=env, capture_output=True, text=True, timeout=10)
    assert result.returncode == 1
    assert f'Missing {tool}' in result.stderr
    assert 'Install Node.js' in result.stderr


@pytest.mark.skipif(os.name != "nt", reason="Windows PowerShell execution policy")
@pytest.mark.parametrize("line_ending", ["\n", "\r\n"], ids=["lf", "crlf"])
@pytest.mark.parametrize("exit_code", [0, 7])
def test_build_cmd_under_restricted_policy(tmp_path, line_ending, exit_code):
    root = Path(__file__).resolve().parents[1]
    scripts = tmp_path / "project with spaces" / "scripts"
    scripts.mkdir(parents=True)
    other = tmp_path / "other cwd"
    other.mkdir()
    wrapper = scripts / "build-ui.cmd"
    wrapper.write_bytes((root / "scripts/build-ui.cmd").read_text(encoding="utf-8")
                       .replace("\n", line_ending).encode("utf-8"))
    target = scripts / "build-ui.ps1"
    target.write_text(
        "@{ policy = [string](Get-ExecutionPolicy); argv = @($args); "
        "cwd = (Get-Location).Path; module_path = $env:PSModulePath } | ConvertTo-Json -Compress | "
        "Set-Content -Encoding UTF8 $env:BUILD_TEST_CAPTURE\n"
        "exit [int]$env:BUILD_TEST_EXIT\n", encoding="utf-8")
    capture = tmp_path / "capture.json"
    clean_env = {key: value for key, value in os.environ.items() if key.upper() != "PSMODULEPATH"}
    env = {**clean_env, "PSExecutionPolicyPreference": "Restricted",
           "BUILD_TEST_CAPTURE": str(capture), "BUILD_TEST_EXIT": str(exit_code)}
    # Simulate an incompatible inherited module (pwsh -> Python/CMD -> WinPS).
    # The build wrapper must restore native module discovery for its child.
    module_dir = tmp_path / "foreign modules" / "Microsoft.PowerShell.Utility"
    module_dir.mkdir(parents=True)
    (module_dir / "Microsoft.PowerShell.Utility.psd1").write_text(
        "@{ ModuleVersion = '99.0'; PowerShellVersion = '99.0'; RootModule = 'invalid.psm1' }",
        encoding="ascii")
    env["PSModulePath"] = str(module_dir.parent) + ";" + os.environ.get("PSModulePath", "")
    # Independent read-only policy queries use native module discovery. The
    # launch probes below retain Restricted and the incompatible module path.
    policy_command = ["powershell.exe", "-NoLogo", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command",
                      "Get-ExecutionPolicy -List | ConvertTo-Json -Compress"]
    policy_before = subprocess.run(policy_command, env=clean_env, capture_output=True, text=True,
                                   timeout=25)
    assert policy_before.returncode == 0, (policy_before.stdout, policy_before.stderr)
    before = policy_before.stdout
    # Reproduce the reported failure without changing any persisted policy.
    blocked = subprocess.run(["powershell.exe", "-NoLogo", "-NoProfile", "-File", str(target)],
                             env=env, capture_output=True, text=True, timeout=25)
    assert blocked.returncode != 0
    assert "UnauthorizedAccess" in blocked.stderr
    assert not capture.exists()
    command = '"' + str(wrapper) + '" alpha "two words"'
    result = subprocess.run(command, shell=True, cwd=other, env=env, input="\n",
                            capture_output=True, text=True, timeout=25)
    assert result.returncode == exit_code, (result.stdout, result.stderr)
    actual = json.loads(capture.read_text(encoding="utf-8-sig"))
    assert actual["policy"] == "Bypass"
    assert actual["argv"] == ["alpha", "two words"]
    assert Path(actual["cwd"]).resolve() == other.resolve()
    assert str(module_dir.parent).casefold() not in actual["module_path"].casefold()
    policy_after = subprocess.run(policy_command, env=clean_env, capture_output=True, text=True,
                                  timeout=25)
    assert policy_after.returncode == 0, (policy_after.stdout, policy_after.stderr)
    after = policy_after.stdout
    assert after == before  # No persisted policy changes; both query children use Bypass.
