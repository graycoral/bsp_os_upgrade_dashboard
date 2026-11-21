# PORT-013 · 직결 보드 커넥터 · 자율 실행 묶음 · 양방향 진단 · 직접 프록시

- **대상 결정·요구사항:** `D-83`, `RQ-77`~`RQ-81` (`T-291`~`T-305`)
- **원본 기준선:** `14e640247a9e17567bc03a8171bbee437b1060ed`
- **대상 코드 커밋:** `b71653b` (직결·자율 실행·양방향 진단 본체) + `85f7f05` (리뷰 `F-01`~`F-08` 수정·`run.sh` `--home` 분리·폴더 복사 전달·`watch_connection`; 후속 대시보드 작업 삭제/재실행·`Test 현황` 전체 TC 토글·회사 `8765` 격리는 [PORT-014](PORT-014.md) 참조)
- **상태:** `LOCAL_IMPLEMENTED_AND_REVIEWED` (Node 22+ `npm run build` 및 실장비 `T-305` 별도)
- **선행 조건:** [PORT-009](PORT-009.md), [PORT-011](PORT-011.md), [PORT-012](PORT-012.md)

## 1. 이식 범위 및 핵심 변경 위치

| 영역 | 주요 파일 | 회사 적용 시 조정/확인 포인트 |
|---|---|---|
| **공통 설정 분리 · 복구 호환** | `backend/gui_test/core/shared_settings_store.py`, `timeouts.py`, `shared_settings.py`, `core/retention.py`, `api/storage.py`, `runtime.py`, `apps/agent-monitor/recovery.py` | 회사 runtime의 `runs.db`/`gui-test-settings.json`에서 1회 자동 이관 확인; **`recovery.py` `RESET_TABLES['connector-registry.db']`에 `'direct_cache'`와 `'shared-settings.db'`를 반드시 함께 반영** (기존 4개 테이블만 고정 시 `reset`이 `RESET_BLOCKED`로 실패) |
| **양방향 진단 · bootstrap-v2** | `backend/gui_test/core/connector_diagnostics.py`, `core/connector_bootstrap.py`, `connector/bootstrap.py`, `connector/shared_control.py`, `apps/agent-monitor/plugin_delivery.py` | Linux `/proc/net/tcp{,6}`·`uid=0` `sshd` 구분 및 `bootstrap-v2` 적용 |
| **Windows SSH -R 수명 분리 · 브리지** | `backend/gui_test/connector/ssh_tunnel.py`, `connector/supervisor.py`, `connector/emergency.py`, `execution/launch.py`, `scripts/setup_runtime.py` | Windows OpenSSH `LogLevel=VERBOSE` 출력·`icacls` 키 ACL·DPAPI `manager-bridge` 동작 확인 |
| **자율 실행 묶음 · 실패 분석 래치** | `backend/gui_test/execution/connector_runs.py`, `execution/host.py`, `execution/batches.py`, `execution/retention.py`, `execution/session_deletion.py`, `connector/console.py` | `executions.db` v2 스키마 자동 마이그레이션, `D-48` `/v1/flash-tests`와 `Host.lock` 배타 유지 확인 |
| **플러그인 독립 클라이언트 · 전달** | `backend/gui_test/standalone/direct_connector_client.py` (`watch_connection` 포함), `standalone/plugin_commands.py` (`connect --watch`), `apps/agent-monitor/plugin.py`, `apps/agent-monitor/plugin_delivery.py` (`windows_directory`, ZIP 제거), `apps/agent-monitor/manage.py` (`prepare-env`), `run.sh` (`--home` 체크아웃별 분리) | 회사 플러그인 Git의 `/bsp-upgrade` 진입점과 `--connector-port` vs `--port` 옵션 연결; `connect --watch`로 `127.0.0.1:8771` 주기 감시; 보드 커넥터는 `<플러그인-전달>/agent-monitor/` 폴더 전체 복사(ZIP 미사용); 회사 대시보드 `run.sh`도 `--home` 분리 정렬 |
| **Agent Monitor 직접 프록시 · UI** | `backend/gui_test/connector/direct_proxy.py`, `connector/registry.py`, `connector/api.py`, `backend/api/main.py`, `standalone/integration.py`, `scripts/serve_monitor.py`, `packages/gui-test-ui/src/ConnectorMirror.tsx`, `SharedControl.tsx`, `apps/web/src/main.tsx`, `packages/gui-test-ui/src/connector_web/view.mjs`, `style.css`, `connector/web_actions.py`, `connector/preview.py`, `connector/gui.py` | 원본 전달 담당자는 두 UI를 빌드하고 자산을 검증한다. 회사가 UI 소스를 수정하거나 자체 빌드하면 Node 22+ 환경에서 `bash scripts/build-ui.sh`로 다시 빌드한다. 배포 시 [PORT-011의 폴더 절차](PORT-011.md#현재-유효-기준)를 따른다. |

## 2. 보존해야 하는 정책

- `D-48` `/v1/flash-tests` 수동 기본 원칙·자동 프로파일 파이프라인·사람 최종 검토.
- `D-77` `--force-stop`, `D-78` 모델 단계 정책, `D-81` 웹 커넥터 좌우 분할, `D-82` 모듈 콤보박스·시작 내부 검사.
- `FLASHING` 중 `taskkill /T /F` 금지, 원격 `-R` 포트 임의 폴백 금지, `StrictHostKeyChecking=no` 금지, 분석 래치 활성 중 수동 `resume` 차단(`409 ANALYSIS_LATCH_ACTIVE`).

## 3. 회사 검증 및 미완료 항목

- 직결 본체의 당시 로컬 Python 루프백/모의 427 + 212 PASS (`tests/test_direct_connector_unit*.py` 포함). 해당 실행의 Hydrogen 독립 검토는 NOT_REVIEWED이며, 위 상태는 후속 `85f7f05`의 F-01~F-08 검토 반영을 포함한다. [본체 실행 기록](../testing/runs/20261119-direct-connector-implementation.md).
- **회사 전달 전 필수:** (1) Node 22+ 환경에서 공급자 UI 빌드(`npm run build`) 및 전달본 자산 검증, (2) 별도 독립 리뷰 세션 완료, (3) `T-305`(`DCA-15`) 실물 Windows OpenSSH·COM·PuTTY·`fastboot`·Linux `sshd` 인수.
