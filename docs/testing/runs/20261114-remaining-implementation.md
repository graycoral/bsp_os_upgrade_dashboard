# 남은 로컬 구현 · 2026-11-14

기준 HEAD `e4f53ca1ec288feb3eb1b9ccff8335a398ad321c` 위 작업 중 변경이다. 새 커밋·배포 ZIP·EXE는 생성하지 않았다. 회사 접점을 제외한 구현과 최종 로컬 검증을 완료했다. 별도 Astra/xhigh 코드 리뷰 **APPROVED**, 검토 범위의 미해결 P1/P2 없음. [독립 기록](20261114-remaining-code-review.md)을 따른다. RQ-68/D-72/T-251~256/REG-0089.

## 범위

| 기능 | 구현 접점 | 검증 상태 |
|---|---|---|
| 실패 분석 실행·조치 후 재시도 | `standalone/analysis_runtime.py`, Worker 분석 callback, 실패 분석 API | 최종 통합 회귀 PASS. 기본 진단 HOLD·등록 명령/검증기·lease/CAS 확인. 회사 분석 도구 NOT_RUN |
| BSP 모듈 TC 재시도 | `core/failure_analysis.py`, `core/manager.py`, 모듈 선택·수신 검증 | 현재 모듈 수락/guard·부모/자식/분석 원자성 회귀 PASS. 실제 BSP 모듈 인수 NOT_RUN |
| 서버·Windows 스냅샷 자동 정리 | `core/retention.py`, `execution/retention.py`, `api/storage.py`, Worker·Host·생산자 잠금 | 아래 임시 디렉터리 시험 PASS. 사용자 runtime 정리 미실행 |
| 설치·업데이트·복구와 공개 도구 준비 | `apps/agent-monitor/manage.py`, bootstrap·공통 스크립트 | 설치/이관/복구 모의 회귀 PASS. 실제 회사 권한·프록시·오프라인 설치 NOT_RUN |
| 커넥터 설정 탭·저장 공간 제어 | 공유 React UI, 브라우저 커넥터, Qt 호환 패널 | Qt 저장/충돌·예상 정리 회귀 PASS. 브라우저·UI 빌드는 아래 근거와 최종 통합 결과를 구분 |

## 스냅샷 정리 계약

- 기본 자동 정리 ON, 7일, 서버·Windows 각각 20 GiB. 생성 후 1시간 이내 자료는 전송·요청 수락 대기 보호 대상으로 남긴다. 5분마다 기존 Worker/Host가 정리하며 새 실행 소유자는 만들지 않는다. 한 주기에 최대 32개를 격리하며 남은 대상은 `batch_limited=true`로 표시한다.
- Linux는 현재 소스, 완료 PASS가 아닌 Run, 과거 실패 근거가 있는 Run, 준비 중·만료 전 준비 영수증의 참조를 보존한다. Windows는 종료 확인·성공이 확인된 실행 사본과 참조 없는 게시 캐시만 정리한다. UNKNOWN·보유 batch·실패 근거를 보존한다.
- DB 실행·결과·이벤트·로그를 삭제하지 않는다. Windows 재개 가능한 `installer-transfers` 업로드는 자동 정리 대상에서 제외한다. 심볼릭 링크·junction·특수 파일·알 수 없는 디렉터리는 건너뛰고 보고한다.
- 트리 순회·용량 계산은 잠금 밖에서 한다. 짧은 생산자 잠금·DB 트랜잭션에서 현재 참조를 다시 확인하고 정리 대상을 격리 이름으로 원자 이동한다. 격리 사본의 실제 삭제는 잠금 해제 후 수행한다. 중단된 격리 사본은 이후 주기에 다시 정리한다. Windows 게시 완료 시 유예 기간을 갱신하고, 지운 설치 캐시의 READY 영수증을 무효화한다.
- 용량은 강제 상한이 아니다. 보호 자료로 목표를 넘으면 `protected_bytes`, `over_budget`를 표시한다. 읽지 못한 경로가 있으면 `measurement_complete=false`다. `dry_run=true`는 예상 결과만 반환한다.
- 설정은 revision CAS로 저장한다. 중앙에서 명시 저장한 정책만 커넥터에 전달하며 runner identity를 확인한다. 연결 실패는 `SYNC_PENDING`으로 남겨 재시도한다. 기본값이 독립 커넥터의 정책을 덮어쓰지 않는다.
- 설정 파일은 `snapshot-storage-policy-v1` JSON이다. `PluginClient.export_storage_policy/import_storage_policy` 또는 `python -m backend.gui_test.core.retention --database <기존 GUI DB> export|apply <파일>`을 사용한다. import는 저장 시점 revision을 검사한다.

## 스냅샷·연결 회귀 실행

전체 로그는 로컬 전용 `.local-reports/`에 보존하고 Git에 포함하지 않는다. 모든 시험은 임시 디렉터리·모의 HTTP·Qt offscreen에서 수행했다.

| 실행 | 명령 | 결과 | 로컬 로그 |
|---|---|---|---|
| 1 | `PATH=/usr/bin:/bin:$PATH .venv/bin/python -m pytest -q backend/gui_test/tests/test_retention.py backend/gui_test/tests/test_sources.py backend/gui_test/tests/test_failure_analysis.py` | exit 0 · 73 PASS | `.local-reports/20261114-snapshot-retention-01/pytest.log` |
| 2 | `PATH=/usr/bin:/bin:$PATH .venv/bin/python -m pytest -q backend/gui_test/tests/test_retention.py backend/gui_test/tests/test_sources.py backend/gui_test/tests/test_failure_analysis.py backend/gui_test/tests/test_plugin_integration_snapshots.py backend/gui_test/tests/test_plugin_integration_batches.py backend/gui_test/tests/test_plugin_integration_service.py backend/gui_test/tests/test_shared_control.py backend/gui_test/tests/test_flashing.py` | exit 0 · 160 PASS | `.local-reports/20261114-snapshot-retention-02/pytest.log` |
| 3 | `PATH=/usr/bin:/bin:$PATH QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q backend/gui_test/tests/test_retention.py backend/gui_test/tests/test_shared_connector_control.py backend/gui_test/tests/test_plugin_integration_service.py backend/gui_test/tests/test_plugin_integration_http.py backend/gui_test/tests/test_plugin_integration_package.py backend/gui_test/tests/test_shared_control.py` | exit 0 · 84 PASS | `.local-reports/20261114-snapshot-retention-03/pytest.log` |
| 4 · P1 수정 후 | `PATH=/usr/bin:/bin:$PATH QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q backend/gui_test/tests/test_retention.py backend/gui_test/tests/test_sources.py backend/gui_test/tests/test_failure_analysis.py backend/gui_test/tests/test_plugin_integration_snapshots.py backend/gui_test/tests/test_plugin_integration_batches.py backend/gui_test/tests/test_plugin_integration_service.py backend/gui_test/tests/test_shared_control.py backend/gui_test/tests/test_flashing.py backend/gui_test/tests/test_shared_connector_control.py` | exit 0 · 189 PASS | `.local-reports/20261114-snapshot-retention-04/pytest.log` |
| 5 · 다른 프로세스 잠금·종료 대기 | `PATH=/usr/bin:/bin:$PATH QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q backend/gui_test/tests/test_retention.py backend/gui_test/tests/test_windows_runner.py` | exit 0 · 45 PASS | `.local-reports/20261114-snapshot-retention-05/pytest.log` |
| 6 · READY 재사용 보호 | `PATH=/usr/bin:/bin:$PATH QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q backend/gui_test/tests/test_retention.py backend/gui_test/tests/test_plugin_integration_transport.py backend/gui_test/tests/test_plugin_integration_pipeline.py` | exit 0 · 30 PASS | `.local-reports/20261114-snapshot-retention-06/pytest.log` |
| 7 · 한 주기 32개 제한 | `PATH=/usr/bin:/bin:$PATH QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q backend/gui_test/tests/test_retention.py` | exit 0 · 19 PASS | `.local-reports/20261114-snapshot-retention-07/pytest.log` |

각 실행은 해당 시점 변경을 검증했다. 뒤의 시험 집합을 앞의 모든 시험에 대한 재실행으로 해석하지 않는다. Starlette TestClient의 httpx 호환 경고 1건이 있었다. 실제 Windows 프로세스·파일 잠금·장비 인수는 이 결과에 포함되지 않는다.

상위 작업의 커넥터 브라우저 11 PASS와 두 UI 빌드 PASS 근거는 `.local-reports/20261114-remaining-implementation/connector-browser-01.log`, `ui-build-01.log`다. Monitor 첫 실행 `monitor-browser-01.log`는 health instance_id 불일치로 FAIL, 두 번째 `monitor-browser-02.log`는 5 PASS / 비동기 assertion 경합 1 FAIL이며 수정 후 최종 6 PASS이며 아래 통합 근거를 따른다. 정확한 명령과 최종 결과는 통합 검증 완료 시 추가한다.

독립 리뷰가 재현한 P1은 정리 중 전체 트리 순회가 SQLite writer/Windows control 잠금을 오래 보유하는 문제였다. 재현 근거는 `.local-reports/20261114-remaining-code-review/retention-lock-repro-02.log`다. 최초 재현 로그의 macOS /var 심볼릭 링크 fixture 오류도 보존했다. 순회·삭제를 잠금 밖으로 옮기고 참조 재검증·원자 격리만 잠금 안에 두도록 수정했다. 느린 순회·삭제·업로드 중 DB 쓰기와 Host 제어 잠금 사용을 확인하는 회귀를 추가했다.

## 남은 검증

- 독립 리뷰 지적 반영 후 최종 영향 회귀 PASS, Astra/xhigh APPROVED. 실제 회사 인수와 구분한다.
- 실제 Windows 11/Python 3.13, 회사 SSH·8765 서비스, COM·fastboot·이미지 플래싱·TC·분석 도구·ACON: NOT_RUN.
- 실제 사용자 runtime의 삭제·회사 설치·실장비 실행: 수행하지 않음.


## 최종 통합 검증

환경은 macOS arm64, CPython 3.11.7, Node 22.23.4, 고정 Playwright Chromium이다. 아래 실행 집합은 중복되므로 합산하지 않는다. 로그·스크린샷·manifest는 로컬 전용이며 Git에 포함하지 않는다.

| 실행 | 결과 | 로컬 로그 |
|---|---|---|
| GUI Test 전체 + 전달/관리/복구 + launcher/setup/build/layout | **1009 PASS / 24 SKIP**, exit 0 | `.local-reports/20261114-remaining-implementation/broad-python-04.log` |
| 설치·복구 담당 최종 집중 | 147 PASS / 13 SKIP, exit 0 | `.local-reports/plugin-centric-implementation-20261114/shared-expanded-final7.log` |
| 브라우저 커넥터 탭·저장 공간·권한·초안·다중 보드 입력 | **13 PASS**, exit 0 | `.local-reports/20261114-remaining-implementation/connector-browser-03.log` |
| Agent Monitor 설정·분석·정리 CAS/양쪽 보고서 | **6 PASS**, exit 0 | `.local-reports/20261114-remaining-implementation/monitor-browser-04.log` |
| Agent Monitor + 단독 GUI Test UI typecheck/build | 두 빌드 PASS, exit 0 | `.local-reports/20261114-remaining-implementation/ui-build-03.log` |

최종 Python 명령:

```bash
PATH=/usr/bin:/bin:$PATH QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest  backend/gui_test/tests tests/test_agent_monitor_delivery.py  tests/test_agent_monitor_manager.py tests/test_agent_monitor_lifecycle.py  tests/test_agent_monitor_recovery.py tests/test_board_connector_launcher.py  tests/test_setup_runtime.py tests/test_build_entrypoint.py tests/test_setup_commands.py  tests/test_gui_test_layout.py tests/test_editable_runner_build.py -q -o faulthandler_timeout=45
```

브라우저 명령은 같은 로컬 Node bin을 PATH에 두고 고정 Chromium의 PLAYWRIGHT_BROWSERS_PATH를 지정해 실행했다.

```bash
.venv/bin/python scripts/test_connector_browser.py
BSP_E2E_PORT=18771 .venv/bin/python scripts/test_dashboard_browser.py shared-control.spec.ts --reporter=line
bash scripts/build-ui.sh
```

24 SKIP은 Windows 전용 등 현재 플랫폼 조건이다. 실제 Windows 11/3.13 검증으로 대체하지 않는다. 경고 28건은 Starlette/httpx TestClient deprecation이다. UI의 큰 화면/390px 화면·탭 선택·키보드 이동을 모의 Chromium으로 확인했고 데스크톱 캡처에서 로그 탭을 직접 확인했다.

추가 실패 이력: `analysis-01.log`, `broad-python-01.log`는 없는 시험 파일명을 지정해 수집 실패했다. `broad-python-02.log`는 Manager를 __new__로 만든 기존 fixture의 control_lock 누락 1 FAIL·711 PASS 후, Mac killpg 권한 오류가 실행 thread 밖으로 빠져나가 중단했다. fixture에 실제 잠금을 준비하고 ProcessTree의 확인/종료 권한 오류를 종료 불명으로 반환하도록 수정했다. EPERM/EACCES 회귀와 실제 로컬 Runner 시험을 추가했다. `runner-followup-01.log`의 health 검사 1 FAIL은 비loopback TestClient fixture의 403이며 정상 loopback으로 수정했고 후속 45 PASS다. `web-api-01.log` 35 PASS는 정리 bridge와 CSRF 차단을 포함한다. `broad-python-03.log` 1006 PASS 뒤 추가된 안전성 시험까지 최종 1009 PASS로 재확인했다. 실패 로그를 지우거나 검사를 약화하지 않았다.

DB schema version 변경 없이 기존 documents/meta를 사용한다. 설정 JSON과 runtime 소유권은 보존하며 초기 이관은 검사 revision과 백업 후 수행한다. 정리된 성공 캐시는 원본에서 다시 준비한다. 기본 분석은 HOLD이고 회사 분석·검증기 등록 없이 조치 성공을 만들지 않는다.

검증 기준 manifest: `.local-reports/20261114-remaining-implementation/final-source-and-tests.json`. 소스(삭제 목록·빌드 자산 포함) SHA256 `0c8b3961316254703678f7fe180b1e21052b89b9986e69ab1641da4fa073a74f`, 시험 SHA256 `dd87cfb15c2113706a8d6ebf676e88b9c666cb6baf2474e43659221cec184d1f`. 새 커밋·푸시는 수행하지 않았다.

독립 리뷰어 실행은 Python432 PASS/19 SKIP, 최종 증분78 PASS, 브라우저13 PASS다. 위 부모 실행과 별도이며 건수를 합산하지 않는다. 리뷰 대상71파일 manifest SHA256 `e45926f045046da7530935fa810b8b79a6bb8991575c52ffa9e501e14910f116`, 로컬 `.local-reports/20261114-remaining-code-review/reviewed-source.json`. 문서49개 상대 링크 검사와 `git diff --check` PASS.
