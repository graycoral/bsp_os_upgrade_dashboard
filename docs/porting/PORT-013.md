# PORT-013 · 직결 보드 커넥터 · 자율 실행 묶음 · 양방향 진단 · 직접 프록시

- **대상 결정·요구사항:** `D-83`, `RQ-77`~`RQ-81` (`T-291`~`T-305`)
- **원본 기준선:** `14e640247a9e17567bc03a8171bbee437b1060ed` + 미커밋 구현(`LOCAL_IMPLEMENTED_NOT_REVIEWED`; 전달 전 커밋 고정 및 별도 독립 리뷰 완료 필요)
- **선행 조건:** [PORT-009](PORT-009.md), [PORT-011](PORT-011.md), [PORT-012](PORT-012.md)

## 1. 이식 범위 및 핵심 변경 위치

| 영역 | 주요 파일 | 회사 적용 시 조정/확인 포인트 |
|---|---|---|
| **공통 설정 분리 · 복구 호환** | `backend/gui_test/core/shared_settings_store.py`, `timeouts.py`, `shared_settings.py`, `core/retention.py`, `api/storage.py`, `runtime.py`, `apps/agent-monitor/recovery.py` | 회사 runtime의 `runs.db`/`gui-test-settings.json`에서 1회 자동 이관 확인; `recovery.py` `RESET_TABLES`의 `shared-settings.db` 및 `direct_cache` 누락 금지 |
| **양방향 진단 · bootstrap-v2** | `backend/gui_test/core/connector_diagnostics.py`, `core/connector_bootstrap.py`, `connector/bootstrap.py`, `connector/shared_control.py`, `apps/agent-monitor/plugin_delivery.py` | Linux `/proc/net/tcp{,6}`·`uid=0` `sshd` 구분 및 `bootstrap-v2` 적용 |
| **Windows SSH -R 수명 분리 · 브리지** | `backend/gui_test/connector/ssh_tunnel.py`, `connector/supervisor.py`, `connector/emergency.py`, `execution/launch.py`, `scripts/setup_runtime.py` | Windows OpenSSH `LogLevel=VERBOSE` 출력·`icacls` 키 ACL·DPAPI `manager-bridge` 동작 확인 |
| **자율 실행 묶음 · 실패 분석 래치** | `backend/gui_test/execution/connector_runs.py`, `execution/host.py`, `execution/batches.py`, `execution/retention.py` | `executions.db` v2 스키마 자동 마이그레이션, `D-48` `/v1/flash-tests`와 `Host.lock` 배타 유지 확인 |
| **플러그인 독립 클라이언트** | `backend/gui_test/standalone/direct_connector_client.py`, `standalone/plugin_commands.py`, `apps/agent-monitor/plugin.py`, `apps/agent-monitor/manage.py` (`prepare-env`) | 회사 플러그인 Git의 `/bsp-upgrade` 진입점과 `--connector-port` vs `--port` 옵션 연결 |
| **Agent Monitor 직접 프록시 · UI** | `backend/gui_test/connector/direct_proxy.py`, `connector/registry.py`, `connector/api.py`, `backend/api/main.py`, `standalone/integration.py`, `scripts/serve_monitor.py`, `packages/gui-test-ui/src/ConnectorMirror.tsx`, `apps/web/src/main.tsx`, `packages/gui-test-ui/src/connector_web/view.mjs`, `connector/web_actions.py`, `connector/preview.py`, `connector/gui.py` | **회사 빌드 환경(Node 22+)에서 `apps/web` 및 `packages/gui-test-ui` UI 빌드(`npm run build`) 재실행 필수** |

## 2. 보존해야 하는 정책

- `D-48` `/v1/flash-tests` 수동 기본 원칙·자동 프로파일 파이프라인·사람 최종 검토.
- `D-77` `--force-stop`, `D-78` 모델 단계 정책, `D-81` 웹 커넥터 좌우 분할, `D-82` 모듈 콤보박스·시작 내부 검사.
- `FLASHING` 중 `taskkill /T /F` 금지, 원격 `-R` 포트 임의 폴백 금지, `StrictHostKeyChecking=no` 금지, 분석 래치 활성 중 수동 `resume` 차단(`409 ANALYSIS_LATCH_ACTIVE`).

## 3. 회사 검증 및 미완료 항목

- 로컬 Python 루프백/모의 427 + 212 PASS (`tests/test_direct_connector_unit*.py` 포함).
- **회사 전달 전 필수:** (1) Node 22+ 환경 UI 빌드(`npm run build`), (2) 별도 독립 리뷰 세션 완료, (3) `T-305`(`DCA-15`) 실물 Windows OpenSSH·COM·PuTTY·`fastboot`·Linux `sshd` 인수.
