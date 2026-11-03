# Windows build execution policy: separate GPT-6-sol verification

- Run ID: 20261103-build-execution-policy-sol
- Date: 2026-11-03 KST
- Executor: GPT-6-sol; local Windows PowerShell and CMD
- Scope: REG-0036 restricted-policy entrypoint regression, setup runtime regression, real local UI builds
- Code base: `fix/build-execution-policy` at `e86c5cb` with uncommitted `scripts/build.cmd` change (diff hash `1248dcba4d00e9f5c1409f3842216384211e1359`) and `tests/test_build_entrypoint.py`
- Environment: Windows; Python 3.13.5, Node 24.21.0, npm 11.19.0, Vite 7.3.7. Existing `apps/web/node_modules` from the original workspace was exposed to this isolated worktree through a temporary junction. No dependency installation was run.

| Test | Command | Result | Evidence |
|---|---|---|---|
| REG-0036 Windows Restricted reproducer | `python.exe -X utf8 -m pytest -q -p no:cacheprovider --basetemp C:\Users\grayc\work\dashboard\bsp_build_tmp1 tests/test_build_entrypoint.py` | PASS: 4 passed in 7.97 s | Real PowerShell rejects direct `-File` with `UnauthorizedAccess`; `build.cmd` launches sibling script with child `Bypass`, forwards arguments and exit code from another directory for LF/CRLF cases. |
| Setup runtime regression | `python.exe -X utf8 -m pytest -q -p no:cacheprovider --basetemp C:\Users\grayc\work\dashboard\bsp_setup_tmp1 tests/test_setup_runtime.py` | PASS: 49 passed, 4 skipped in 7.34 s | Platform-specific Linux tests skipped on Windows. |
| Both UI builds | `cmd.exe /d /c "scripts\build.cmd -Target all -SkipInstall"` | PASS: exit 0 | Dashboard Vite production build: 1583 modules; standalone GUI test build: 30 modules. Output at ignored `apps/web/dist` and `gui_test/static` in this worktree. |

`python.exe` in the two test commands was `C:\Users\grayc\work\dashboard\bsp_os_upgrade_dashboard\.local-reports\python313\python.exe`. The real UI build ran under the existing Process `RemoteSigned` policy; the four regression cases independently supplied an inherited `Restricted` policy to real Windows child processes. `Get-ExecutionPolicy -List` before and after the tests and build remained: MachinePolicy Undefined, UserPolicy Undefined, Process RemoteSigned, CurrentUser Undefined, LocalMachine Undefined.

This verifies local shell launching and UI compilation. It does not exercise Linux, hardware, model agents, or external services.

## Follow-up after Windows CI policy-query failure

Windows CI reported `CouldNotAutoloadMatchingModule` for `Microsoft.PowerShell.Security` while the test queried `Get-ExecutionPolicy -List` in a `Restricted` child, before reaching the launch probe. The policy-query children now use command-line `-ExecutionPolicy Bypass` solely to compare persisted scope listings before and after. The direct `-File` probe still inherits `Restricted` and must fail with `UnauthorizedAccess`; the tested `build.cmd` child must run with `Bypass` and preserve arguments and exit code.

- Retest command: `C:\Users\grayc\work\dashboard\bsp_os_upgrade_dashboard\.local-reports\python313\python.exe -X utf8 -m pytest -q -p no:cacheprovider --basetemp C:\Users\grayc\work\dashboard\bsp_build_tmp2 tests/test_build_entrypoint.py`
- Result: **PASS**, 4 passed in 6.12 s (2026-11-03 KST).
- Policy after retest: MachinePolicy Undefined, UserPolicy Undefined, Process RemoteSigned, CurrentUser Undefined, LocalMachine Undefined, matching the earlier listing.
- CI status for the revised test: pending. This local run does not reproduce the CI module-autoload environment.

## Final wrapper retest with module-path cleanup

The wrapper now clears the inherited `PSModulePath` in its local CMD environment before launching Windows PowerShell 5.1. The test injects a fake incompatible `Microsoft.PowerShell.Utility` module path into the wrapper launch; its direct `-File` probe still inherits `Restricted` and asserts `UnauthorizedAccess`.

| Check | Command | Result |
|---|---|---|
| REG-0036 | `C:\Users\grayc\work\dashboard\bsp_os_upgrade_dashboard\.local-reports\python313\python.exe -X utf8 -m pytest -q -p no:cacheprovider --basetemp C:\Users\grayc\work\dashboard\bsp_build_tmp3 tests/test_build_entrypoint.py` | PASS: 4 passed in 7.08 s |
| Setup runtime | Same Python and pytest options, `--basetemp C:\Users\grayc\work\dashboard\bsp_setup_tmp3 tests/test_setup_runtime.py` | PASS: 49 passed, 4 skipped in 6.44 s |
| Dashboard and standalone GUI test builds | `cmd.exe /d /c "scripts\build.cmd -Target all -SkipInstall"` | PASS: exit 0; Vite 7.3.7 transformed 1583 and 30 modules respectively |

Existing installed dependencies were reused through the ignored worktree junction; no install, hardware, service, or external agent operation was performed. After these runs, `Get-ExecutionPolicy -List` again showed Process RemoteSigned and every other scope Undefined.

**Regression sensitivity limit:** In a temporary copy of the wrapper with only `set "PSModulePath="` removed, the fake `Microsoft.PowerShell.Utility` module path still allowed the harmless target to run locally (exit 0 and capture written). A second temporary fake `Microsoft.PowerShell.Security` module also did not fail this local legacy copy. Thus this Windows PowerShell 5.1 host confirms the fixed wrapper works, but its fake-module fixture does not independently prove that clearing `PSModulePath` is necessary. The observed GitHub CI duplicate TypeData failure from inherited PowerShell 7 module paths requires a fresh CI run for that specific fix.

The test was strengthened to capture the child `PSModulePath` and assert that the injected foreign directory is absent. Retest with `--basetemp C:\Users\grayc\work\dashboard\bsp_build_tmp4`: **4 passed in 6.85 s**. In a temporary copy of the wrapper with the clear line removed, the harmless target still exited 0, but the captured child module path **contained the injected foreign directory**. That mutant would fail the new path assertion, confirming the test protects module-path isolation on this host. A fresh Windows CI run is still needed to verify the actual PowerShell 7 to 5.1 module conflict is resolved.
