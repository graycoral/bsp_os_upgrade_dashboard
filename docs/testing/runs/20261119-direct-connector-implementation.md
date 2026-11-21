# 2026-11-19 · 직결 보드 커넥터 · 자율 실행 묶음 · 양방향 진단 구현 검증 기록

- **대상 결정·요구사항:** `D-83`, `RQ-77`~`RQ-81` (`T-291`~`T-305`, 설계 계획 `DCA-01`~`DCA-15`)
- **설계 기준:** [직결 보드 커넥터 상세 설계](../../design/DIRECT_CONNECTOR_ARCHITECTURE.md)
- **구현 상태:** **로컬 모의/루프백 구현 검증 완료 (`LOCAL_IMPLEMENTED_NOT_REVIEWED`)** · 별도 세션 독립 Hydrogen 리뷰 **`NOT_REVIEWED`** · 실장비/회사 환경 인수(`T-305`/`DCA-15`) **`NOT_RUN`**
- **기준선 커밋:** `14e640247a9e17567bc03a8171bbee437b1060ed` (+ 현재 미커밋 구현·시험 워킹트리)

## 1. 구현 범위 요약 (Unit 1 ~ Unit 6)

1. **Unit 1 (`shared-settings.db` · `recovery.py` · `bootstrap-v2` · Linux 진단 프로브)**
   - `backend/gui_test/core/shared_settings_store.py`, `core/timeouts.py`, `core/shared_settings.py`, `runtime.py`, `apps/agent-monitor/recovery.py`, `core/connector_bootstrap.py`, `connector/bootstrap.py`, `connector/shared_control.py`, `apps/agent-monitor/plugin_delivery.py`, `core/connector_diagnostics.py`.
2. **Unit 2 (Windows `SSH -R` 수명 분리 · `LogLevel=VERBOSE` · DPAPI 제어 브리지)**
   - `backend/gui_test/execution/launch.py` (`host-active.json`/`ssh-tunnel.json`), `connector/emergency.py`, `connector/ssh_tunnel.py` (`SshTunnelSupervisor`, `preflight_ssh`, `classify_ssh_stderr_line`, 선택 `-L` 분리), `connector/supervisor.py` (Agent Monitor 필수 게이트 제거, DPAPI `manager-bridge` 재부착, `RESTART_HOST` 중 `SSH -R` 유지), `scripts/setup_runtime.py`.
3. **Unit 3 (`executions.db` 자율 실행 묶음 엔진 · 첫 실패 래치 · 복구 · 보존)**
   - `backend/gui_test/execution/connector_runs.py` (`ConnectorEngine`, DDL §4.5, DPAPI `BridgeTokenStore`, `POST /v1/connector-runs`, 10s 리스 제거, `FLASHING` 안전 경계 중단, `fail-stop-analysis-v1` 단일 `BEGIN IMMEDIATE` 래치, claim/heartbeat/`verifier` 가드/`RETRY` vs `REPREPARE`, `UNKNOWN` 복구/`reconcile`/`DELETE` 톰스톤, UTF-8 안전 byte-offset 로그), `execution/host.py` (`GET /v1/source-snapshots/{id}`, 청크 `/v1/installer-snapshots/{id}`, v1 identity 키 보존), `execution/batches.py`, `execution/retention.py`.
4. **Unit 4 (플러그인 디커플링 · `DirectConnectorClient` · 분석 핸드오프 · TC 투영)**
   - `apps/agent-monitor/manage.py` (`prepare-env`), `apps/agent-monitor/plugin.py` (`--connector-port`/`--monitor-port` 충돌 차단, Agent Monitor 없이 직접 실행), `backend/gui_test/standalone/direct_connector_client.py`, `standalone/plugin_commands.py` (`execute_direct`, 로컬 `connect export`, `KeyboardInterrupt` 분리 추적, `analyze_once`, 오프라인 설정 양방향 병합/충돌 감지).
5. **Unit 5 (`DirectConnectorProxy` · 보안 미들웨어 · Web/Qt/Preview/React UI)**
   - `backend/gui_test/connector/direct_proxy.py`, `connector/registry.py` (`direct_cache`), `connector/api.py` (`/direct/*`), `apps/agent-monitor/recovery.py` (`RESET_TABLES['connector-registry.db']`에 `direct_cache` 반영), `standalone/integration.py` & `backend/api/main.py` (`settings`/`control` 스코프 및 CSRF 검증), `scripts/serve_monitor.py` (10s 주기 백그라운드 프로브), `packages/gui-test-ui/src/connector_web/view.mjs`, `connector/web_assets/host.mjs`, `connector/web_actions.py`, `connector/preview.py`, `connector/gui.py`, `packages/gui-test-ui/src/ConnectorMirror.tsx`, `apps/web/src/main.tsx`.

## 2. 실행한 실제 시험 및 결과

| 구분 | 실행 명령 | 결과 | 비고 / 제약 |
|---|---|---|---|
| **Direct Connector 단위·통합·보안 + 관련 커넥터/미러/플러그인/복구/런처/정책 회귀** | `.venv/bin/pytest -q tests/test_direct_connector_unit1.py tests/test_direct_connector_unit2.py tests/test_direct_connector_unit3.py tests/test_direct_connector_unit4.py tests/test_direct_connector_unit5_and_security.py backend/gui_test/tests/test_connector_bootstrap.py backend/gui_test/tests/test_shared_connector_control.py backend/gui_test/tests/test_connector_server_port.py backend/gui_test/tests/test_connector_web.py backend/gui_test/tests/test_flashing.py tests/test_connector_mirror.py tests/test_connector_mirror_http.py tests/test_plugin_delivery.py tests/test_plugin_runtime.py tests/test_bsp_plugin_client.py tests/test_agent_monitor_recovery.py tests/test_agent_monitor_delivery.py tests/test_api.py tests/test_board_connector_launcher.py tests/test_new_job_tool_policy.py` | **452 PASS, 20 SKIP** | `BypassSandbox: true`; 20 SKIP은 macOS 환경의 Windows 전용 케이스 (2026-11-21 후속 보완·효율성 개선 4건 시험 포함) |
| **D-82 모듈 카탈로그 · D-79 TC 상태 · BSP 오케스트레이션 회귀** | `.venv/bin/pytest -q backend/gui_test/tests/test_module_selection.py tests/test_plugin_module_catalog.py tests/test_orchestration_runtime.py tests/test_connector_test_status.py` | **212 PASS** | `BypassSandbox: true` |
| **문서 정합성 검증** | `.venv/bin/python docs/testing/validate_docs.py` | **PASS** (이 기록 반영 후 재확인) | 아래 확인 참조 |

### 발견 후 수정한 결함(회귀 방지)

1. `backend/gui_test/core/models.py`의 `now()`는 ISO UTC 문자열을 반환하므로 SQLite `REAL` 컬럼/타임스탬프 비교에 사용할 때 `time.time()`을 사용하도록 수정(`connector_runs.py`, `supervisor.py`).
2. `backend/gui_test/connector/supervisor.py` `_probe()`에서 `SimpleNamespace` / `object.__new__(Manager)` 테스트 픽스처에 `runtime` 속성이 없을 때 `getattr(self, 'runtime', self.home / 'runtime')`로 폴백하고 `SshTunnelSupervisor` 인자명을 일치시킴.
3. `backend/gui_test/connector/ssh_tunnel.py`의 `read_stream`이 `bytes` 스트림(비텍스트 모의 Popen)을 안전하게 UTF-8 디코딩하도록 수정하고, `CONNECTING→CONNECTED` 전환 전에 선택 `-L` 초기 검사를 반영하도록 조정.
4. `backend/gui_test/execution/connector_runs.py`에서 `_validate_run_inputs`의 `source_revision` 키 불일치(`manifest['source_revision']`) 및 임시 디렉터리 하위 폴더(`Path(tmp_src) / 'source'`), `decide_analysis` 내 `_serialize_run(c, ...)` 인자 누락을 수정.
5. `backend/gui_test/standalone/direct_connector_client.py`에서 소스 스냅샷 ZIP을 `ZIP_STORED`로 생성하고 `bounded_evidence()` 반환 튜플을 dict로 구조화하며 `SharedSettingsStore` 실제 메서드(`read`, `save`, `read_preferences`, `save_preferences`, `save_timeouts`, `save_storage_policy`)와 정합.
6. `apps/agent-monitor/recovery.py` `RESET_TABLES['connector-registry.db']`에 Unit 5 신규 테이블 `direct_cache`를 등록해 `reset`/`test_agent_monitor_recovery.py` `RESET_BLOCKED` 회귀를 방지.
7. **2026-11-20/21 독립 리뷰 후속 보완 및 1단계 효율성 개선**:
   - `backend/gui_test/standalone/direct_connector_client.py`: `sync_installer_snapshot()` `staged / snap_id` 경로 수정·파일 스트리밍 업로드·`READY` 시 ZIP 생략, `global_defaults`/`module_defaults` 및 POSIX glob 매칭 연동, `shared['connection']` 및 활성 보드 우선 선택, `watch_run()` `eof=True` 완료 스트림 폴링 스킵.
   - `backend/gui_test/standalone/plugin_commands.py`: `test run`/`watch` `FAILURE_STOP_LATCH` 자동 분석 및 `RETRY`/`REPREPARE` 재추적 루프 연결, `--tc-root`·`--module` CLI 옵션 추가.
   - `backend/gui_test/execution/connector_runs.py`: `decide_analysis()` 대상 보드 기준 `HARDWARE_NOT_READY` 검사, `BridgeTokenStore` `(mtime_ns, size)` 캐시, `connector_runs.db` 보조 인덱스 6종 추가.
   - `backend/gui_test/connector/direct_proxy.py`: `_request_windows()` `headers` 파라미터 누락(`rerun_run` `TypeError`) 수정, 영속 `httpx.Client` 재사용 및 `probe_ttl_s`/`max_age_s` 캐시 지원 추가.

## 3. 미검증 항목 및 다음 단계

- **Node/npm UI 빌드:** 현재 macOS 실행 환경에 `node` / `npm`이 설치되어 있지 않아 `apps/web` 및 `packages/gui-test-ui`의 Vite/TypeScript 프로덕션 빌드는 실행하지 못했다(기존 `apps/web/dist/` 산출물은 그대로 보존). Node 22+ 환경 또는 회사 이식 시 `npm run build` 검증 필수.
- **실장비·실환경 인수 (`T-305` / `DCA-15`):** 실제 Linux `sshd`, Windows 11 OpenSSH 8.x/9.x DPAPI, 실물 COM 멀티플렉서·PuTTY·`fastboot` 보드 환경 검증은 `NOT_RUN`.
- **독립 리뷰:** 별도 Hydrogen 리뷰 세션은 아직 수행 전이므로 **`NOT_REVIEWED`**.
