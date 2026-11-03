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
    wrapper = scripts / "build.cmd"
    wrapper.write_bytes((root / "scripts/build.cmd").read_text(encoding="utf-8")
                       .replace("\n", line_ending).encode("utf-8"))
    target = scripts / "build.ps1"
    target.write_text(
        "@{ policy = [string](Get-ExecutionPolicy); argv = @($args); "
        "cwd = (Get-Location).Path } | ConvertTo-Json -Compress | "
        "Set-Content -Encoding UTF8 $env:BUILD_TEST_CAPTURE\n"
        "exit [int]$env:BUILD_TEST_EXIT\n", encoding="utf-8")
    capture = tmp_path / "capture.json"
    env = {**os.environ, "PSExecutionPolicyPreference": "Restricted",
           "BUILD_TEST_CAPTURE": str(capture), "BUILD_TEST_EXIT": str(exit_code)}
    policy_command = ["powershell.exe", "-NoLogo", "-NoProfile", "-Command",
                      "Get-ExecutionPolicy -List | ConvertTo-Json -Compress"]
    before = subprocess.run(policy_command, env=env, capture_output=True, text=True,
                            check=True, timeout=25).stdout
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
    after = subprocess.run(policy_command, env=env, capture_output=True, text=True,
                           check=True, timeout=25).stdout
    assert after == before  # Process / user / machine policy unchanged outside child.
