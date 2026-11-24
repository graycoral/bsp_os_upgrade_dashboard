# PORT-014 · 대시보드 작업 삭제/재실행 · Test 현황 전체 TC/자율 실행 · 회사 8765 격리

- **선행 조건:** [PORT-013](PORT-013.md) (`b71653b`)
- **원본 기준선:** `b71653b`
- **대상 코드 커밋:**
  - `ed6a6f0`: `Test 현황` 공통 `tc_root` 카탈로그 폴백 · `전체 TC 보기` 토글 · `PluginModules` 게시 안내
  - `3e6e4a8`: `Test 현황` 보드 커넥터 자율 실행 표시/제어 · BSP 작업 삭제(`DELETE /api/v1/jobs/{id}`) · 전체 진행률/종합 진행도 단일 박스 통합
  - `d83cc11`: 완료 BSP 작업 `작업 재실행` · 완료 보드 커넥터 자율 실행 `POST /v1/connector-runs/{id}/rerun`
  - 상태: `LOCAL_IMPLEMENTED_NOT_REVIEWED` (Python 단위/API 회귀 `29 passed`, Node 22+ UI 빌드 및 실장비 `T-305` 별도)

## 1. 이식 범위 및 핵심 변경 위치

| 영역 | 주요 파일 | 회사 적용 시 조정/확인 포인트 |
|---|---|---|
| **Test 현황 TC 폴백 · 전체 TC 보기 · 자율 실행** | `backend/gui_test/core/manager.py`, `packages/gui-test-ui/src/TestPage.tsx`, `apps/web/src/PluginModules.tsx` | `SourceService` 미설정 시 `shared-settings` `tc_root` 자동 표시; 모듈 스코프 시 `전체 TC 보기` 켜기/끄기; `/connector/direct/status` 자율 실행 배너 및 제어; `모듈 대상 경로 (JSON 배열)` UI 입력 제거 및 모듈 `선행 모듈` 콤보박스 + 대시보드 `직접 추가` 입력 지원 |
| **BSP 작업 삭제 · 재실행 · 진행률 단일 박스** | `backend/storage/store.py`, `backend/api/main.py`, `apps/web/src/main.tsx`, `apps/web/src/style.css` | `DELETE /api/v1/jobs/{id}` (`RUNNING`/`UNKNOWN`/`lease`/오케스트레이션/조정 레인 활성 시 `409 JOB_ACTIVE` 차단); `COMPLETED` 작업의 `작업 재실행`; `.overall-progress-box` 단일 카드 통합 |
| **자율 실행 재실행 (`rerun`)** | `backend/gui_test/execution/connector_runs.py`, `execution/host.py`, `connector/direct_proxy.py`, `connector/api.py`, `packages/gui-test-ui/src/ConnectorMirror.tsx` | `COMPLETED` 이면서 `analysis_latched=0`인 Run만 `POST /v1/connector-runs/{id}/rerun` 허용 (`409 RERUN_BLOCKED` 그 외 거부); Node 22+ 환경에서 `bash scripts/build-ui.sh` 빌드 필수 |
| **시험** | `tests/test_direct_connector_unit5_and_security.py` | `test_manager_catalog_falls_back_to_shared_tc_root_and_test_page_toggle`, `test_delete_job_endpoint_and_overall_progress_box`, `test_connector_run_rerun_clones_completed_run` |

## 2. 회사 병행 실행 시 포트·경로 격리 기준

- **대시보드 HTTP 포트 분리:** 회사 `bsp-os-upgrade-dashboard`는 **`8765`** 포트를 사용하고, 원본 `agent-monitor`는 기본 **`8766`** 포트를 사용한다.
- **`--home` / `--runtime` 격리:** 회사 `run.sh`에도 `--home "${BSP_HOME:-$root/.monitor-home}"`와 `--runtime "${BSP_RUNTIME:-$root/.runtime}"`를 반드시 반영해, `~/.local/share/bsp-agent-monitor/` 공유로 인한 `runtime-location.json` 충돌과 `stop`/`restart` 간섭을 방지한다.
- **보드 커넥터 포트:** 회사 대시보드(`8765`)에 연결하는 Windows 보드 커넥터는 `board-connector.bat --server-port 8765`를 사용한다. 같은 Linux 호스트에 두 커넥터의 `SSH -R` 터널을 동시에 연결할 때만 한쪽의 `remote_runner_port`(기본 `8771`)와 `--connector-port`를 별도 포트(예: `8775`)로 분리한다.

## 등록된 Windows 실행기의 모듈 TC 목록 수정 (REG-0122)

Test 현황에서 Windows가 연결되어도 선택한 모듈의 TC가 0개로 나오던 문제를 수정했다. 보드 커넥터 탭에 스크립트가 보이고 Test 현황에 “Windows 실행기가 연결되지 않았습니다.”가 표시되는 경우가 해당한다. 이 보완은 기존 PORT-014 모듈 TC 조회와 등록 실행 어댑터를 사용하는 Linux 대시보드에 적용한다.

- 회사에서 모듈 조회를 별도로 구현했다면 `backend/services/module_test_selection.py`의 `ModuleTestSelection.select`에서 실행기 연결 여부를 공개 계약 `runner.readiness()['ready']`로 확인한다. 미등록 또는 등록 후 콘솔 상태 미수신 시에는 조회를 차단한다.
- 전달 패키지의 `agent-monitor/`에서 아래 명령으로 HTTP 회귀 시험을 실행한다. 연결된 모의 실행기는 Ethernet TC 2개만 반환하고 나머지 두 사례는 빈 목록과 미연결 사유를 반환한다. 실제 장비 실행은 회사 인수 범위다.
- 교체 대상은 Linux 대시보드 코드다. DB 마이그레이션이나 Windows 재설치는 필요하지 않다. 회사 릴리스 기록에는 패키지의 `AGENT_MONITOR_SOURCE.json`에 있는 `source_head`와 회사 적용 커밋을 남긴다. 복구 시 기존 runtime을 사용해 직전 검증 릴리스를 다시 선택한다.

```bash
python -m pytest -q backend/gui_test/tests/test_module_selection.py -k registered_windows_module_selection
```
