# RQ-50 local synthetic tests

Run from the repository root with the already installed host toolchain:

```powershell
node workflow_diagram/tests/run.cjs --list
node workflow_diagram/tests/run.cjs
```

For a separately installed compatible host toolchain, set `WORKFLOW_TOOLCHAIN_DIR` to its absolute `node_modules` directory. Optional `BSP_BROWSER_EXECUTABLE` selects an existing browser executable; no dependency or browser installation is performed. The default toolchain is `apps/web/node_modules`. The runner accepts Playwright arguments such as `adapter.spec.ts snapshot.spec.ts` and `--grep T-147`.

| File | Coverage |
| --- | --- |
| adapter.spec.ts | T-144 persisted identity/group validation; T-145 validity, code/build, manual/automatic Test, transitions, progress, malformed snapshots; T-148 pure bounded projection |
| snapshot.spec.ts | T-146 generation/order/version, equivalent-version freshness, delayed failure, explicit reset and timeout recovery |
| presentation.spec.ts | T-146 ACON scope/expiry; T-147 independent execution/connection and selective path activity |
| browser.spec.ts | T-144 structure/keyboard/scope state; T-147 connection/motion/375px; T-148 isolated production build, scoped CSS, 100 modules with 80-character names, DOM and timing metrics |
| host-integration.spec.ts | T-144 task selection; T-146 real application refresh/events/timeout/conflict acceptance; T-148 polling comparison and existing navigation |

`browser.spec.ts` copies only `web`, `adapters`, `host` and synthetic harness files into an owned OS temporary directory. That directory has no `apps/web` or `gui_test`; Vite builds it for production before starting its test server. React and build/test tools come from the explicitly identified external toolchain. `host-integration.spec.ts` deliberately uses the existing application source and intercepts all API calls with synthetic routes. These two suites exercise different integration boundaries.

Performance assertions: 100-module display and expand-all each at most 1500ms; each adapter transformation at most 100ms. Reports print response bytes, JSON parsing time, adapter samples, React render duration/count and observed request counts. The criteria are local acceptance checks, not claims about company hardware. Screenshots, traces and JSON reports are written to `.local-reports/workflow-diagram-*`.

All tests are local mocks. No BSP process, ACON provider, equipment, Jira, credentials or production database is used. T-149 remains a separate live acceptance test. Discovery or syntax checking alone is not a product PASS.
