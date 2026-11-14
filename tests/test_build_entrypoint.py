"""REG-0036: real Windows shell launch under a restricted inherited policy."""
import json
import os
from pathlib import Path
import subprocess

import pytest


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
