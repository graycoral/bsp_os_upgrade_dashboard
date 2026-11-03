# Live Test view independent local verification (2026-11-03)

Base commit: `d8e11b3a4bb9b7276e2da8026b5756d027a95eb1`, branch `feature/live-test-view`. Product and documentation changes were uncommitted during verification. New test files: `gui_test/tests/test_live_view.py`, `tests/e2e/gui-live-view.spec.ts`.

## Scope

- API: dashboard and standalone unconfigured live capabilities, empty catalog/boards/history, no Mock leakage, forged preflight/start rejected, configured manager reuse, disconnected/connected probe, no second manager, offline pause/cancel/control, offline resume block, active cancellation intent.
- Browser: Mock Run created and cancelled; live switch, reload persistence, empty TC/boards/history, disabled execution, forged start 503, switch back to preserved Mock Run. Local API only; no worker, TC, Windows runner, hardware, company network, or model execution.

## Commands and outcomes

1. `.local-reports/python313/python.exe -X utf8 -m pytest gui_test/tests/test_live_view.py -q -p no:cacheprovider --basetemp .local-reports/pytest-live-view-sol` — **6 PASS**, 1 existing `starlette.testclient` deprecation warning.
2. `.local-reports/python313/python.exe -X utf8 -m pytest gui_test/tests -q -p no:cacheprovider --basetemp .local-reports/pytest-live-view-full-gui` — **181 PASS**, same warning.
3. `npm run build` in `apps/web` — **PASS**, Vite 7.3.7; final post-REG-0032 asset `index-Qp_Qrpbo.js`.
4. `npm run build` in `gui_test/web` — **PASS**, Vite 7.3.7; final asset `index-CLqZMIPn.js`.
5. `.local-reports/python313/python.exe -X utf8 .local-reports/run-live-view-browser.py` — **1 PASS** after the REG-0032 fix with installed Chrome, isolated API at 127.0.0.1:8768, no worker. The helper runs `npx.cmd playwright test gui-live-view.spec.ts` from `apps/web` and always terminates its API process. The final test asserts `Test 현황` is visible directly after switching to live, reloading live, and switching back to Mock. Screenshot: `.local-reports/live-view.png`.

## Failed attempts and limits

- Relevant broader regression command: `.local-reports/python313/python.exe -X utf8 -m pytest gui_test/tests/test_api.py gui_test/tests/test_dashboard.py gui_test/tests/test_core.py gui_test/tests/test_live_view.py tests/test_api.py -q -p no:cacheprovider --basetemp .local-reports/pytest-live-view-regression` — **107 PASS / 2 FAIL**. Both failures are in `tests/test_api.py` and use Linux paths (`/fixture/nonexistent`, `/srv/custom bsp`) that `Path.is_absolute()` rejects on Windows. They are outside GUI Test and were not edited.
- `.local-reports/python313/python.exe -X utf8 scripts/test_e2e.py` — **BLOCKED** on Windows: its backend worker imports `fcntl` and exits with `ModuleNotFoundError`. This does not establish a Linux worker or full E2E result.
- First targeted Playwright attempt lacked the bundled Chromium binary; rerun with installed `C:\Program Files\Google\Chrome\Application\chrome.exe` passed.
- **REG-0032 finding preserved:** The first browser version reopened `Test 현황` after each navigation, masking a real UX defect: live/default switch reload landed on the overview. Root fixed `apps/web/src/main.tsx` to initialize the Test tab when `guiExecution=live|default`. The test no longer reopens the tab after those transitions and passed on the rebuilt dashboard. The initial no-query Mock fixture reload still reopens the workspace, matching the existing baseline behavior.
- Actual Windows runner connectivity, hardware, TC execution, and Linux integrated worker remain **NOT_RUN** here.
