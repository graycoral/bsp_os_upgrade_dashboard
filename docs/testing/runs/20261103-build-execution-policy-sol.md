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
