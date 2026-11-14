# 2026-11-14 스크립트 명명·중복 진입점 정리

기준: main `e4f53ca1ec288feb3eb1b9ccff8335a398ad321c`와 기존 설계 WIP. [조사](20261114-script-audit.md) 후 승인된 구현이다. 최종 커밋은 미정이며 이 기록은 이번 로컬 검증에만 적용한다.

## 변경

- UI 빌드는 `scripts/build-ui.{sh,cmd,ps1}`, Windows standalone wheel/ZIP 조립은 `apps/gui-test/build-windows-package.{cmd,ps1}`로 구분했다.
- 편집형 소스 bundle은 `scripts/build-connector-bundle.{cmd,ps1}`와 `build_connector_bundle.py`로 명명했다. 동봉 source allowlist·생성 repack module·고정 source hash 입력·관련 fixture/import를 함께 변경했다.
- API만 실행은 `scripts/serve_monitor.py`, BSP profile 관리는 `scripts/manage_profile.py`, Dashboard 브라우저 회귀는 `scripts/test_dashboard_browser.py`로 명명했다. setup Linux 실행·CI·현재 문서의 호출도 갱신했다.
- `scripts/run.*`, `doctor.*`, `start.sh`, standalone `start.ps1`, 형제 npm `build:gui-test` 별칭을 제거했다. 설정·실행·진단은 기존 `scripts/setup.*`의 하위 명령을 유지한다. 루트 `run.sh`는 별도 공통 lifecycle manager의 `start` 호출로 연결한다. manager 자체 검증은 전체 구현 기록에서 다룬다.
- 새 EXE를 만들지 않는 현재 방향에 따라 `build_windows_runner.py`, PyInstaller spec·build lock을 제거했다. `windows_runner_entry.py`, frozen 호환 경계·과거 EXE opt-in smoke는 보존했다.
- 루트 `board-connector.cmd`, 설치형 공개 CLI, 설정·DB·runtime은 유지한다. 과거 고정 버전 PASS 명령과 배포본 hash 검증은 당시 증거로 보존하고 현재 명령 표를 `scripts/README.md`에 추가했다.

## 검증

전체 출력은 아래 `.local-reports/`의 로컬 전용 파일에 보존했으며 저장소에는 포함하지 않는다. 실제 Windows/회사 장비·SSH·모델 실행이나 새 EXE 생성은 하지 않았다.

| 명령/범위 | 결과 | 로그 |
|---|---|---|
| 초기 10파일 pytest: build entrypoint/setup commands/setup runtime/runner ports/frozen boundary/editable build/runtime/layout/source portability/package | FAIL: 268 PASS, 15 SKIP, 5 FAIL. 제거한 별칭을 호출하던 시험 2건을 현재 setup 명령으로 수정했다. 나머지 3건은 아래 환경 항목이다. | `.local-reports/20261114-script-consolidation-01/pytest.log` |
| 동일 10파일 재시험 | FAIL: 270 PASS, 15 SKIP, 3 FAIL. 별칭 관련 2건은 PASS. | `.local-reports/20261114-script-consolidation-01/pytest-retest.log` |
| `python -m pytest tests/test_build_entrypoint.py tests/test_setup_commands.py tests/test_setup_runtime.py tests/test_runner_ports.py tests/test_windows_runner_bundle.py tests/test_editable_runner_build.py tests/test_gui_test_layout.py backend/gui_test/tests/test_package.py -q` | PASS: 241 PASS, 15 SKIP. Windows 전용은 SKIP이며 Linux/Windows 실환경 인수로 표현하지 않는다. | `.local-reports/20261114-script-consolidation-02/pytest.log` |
| Node 22.23.4 PATH로 `bash scripts/build-ui.sh all --skip-install` | PASS: Dashboard와 standalone GUI UI 빌드. 다른 에이전트의 후속 UI 변경 전 실행이므로 최종 UI 변경 검증은 별도 재실행한다. | `.local-reports/20261114-script-consolidation-01/build-ui.log` |
| `manage_profile.py --help`, `build_connector_bundle.py --help`, `serve_monitor.py --help` | PASS: 각 종료 코드 0 | `.local-reports/20261114-script-consolidation-01/*-help.log` |
| `bash -n run.sh scripts/setup.sh scripts/build-ui.sh`, Python compileall, `git diff --check` | PASS | 로컬 구문/정적 검사 |
| `python docs/testing/validate_docs.py` | PASS: 상대 링크 1365, RQ 66, T 239, 오류 없음 | `.local-reports/20261114-script-consolidation-02/docs.log` |

확인한 잔여 환경 실패는 Mac의 `process_identity`가 시작 직후 자식 identity를 얻지 못하는 1건과 시스템 Git이 `fatal: Not a git repository ...`처럼 대문자 N을 출력해 기존 lowercase 전용 분기와 맞지 않는 folder link 2건이다. 스크립트 정리를 위해 해당 시험을 삭제하거나 production 검사를 약화하지 않았다. Git 진단 수정과 후속 검증은 담당자의 별도 구현 기록을 따른다. 초기 실패 로그를 보존한다.

삭제/이동한 경로의 정적 호출을 조사했다. 잔여 이전 경로는 migration 표, 고정 커밋/과거 실행 근거 또는 이전 EXE 자체의 provenance를 검사하는 opt-in smoke에 한한다. 최종 전체 변경에서 공통 서비스 manager/export와 UI를 합친 회귀, 실제 Windows CMD/PowerShell·Python 3.13·Z:/UNC 및 회사 장비 인수는 이 결과와 별도로 확인한다.

## 공통 서비스·복사형 전달·새 GUI 통합 후 최종 검증

부모 구현의 공통 설정/커넥터 UI와 Agent Monitor manager/export가 준비된 뒤 시험을 추가하고 다시 실행했다. 이 절은 위의 초기·중간 실행을 대체하거나 삭제하지 않는다. 최종 검증도 미커밋 작업 트리의 로컬·모의 결과다.

추가 시험 파일은 `tests/test_agent_monitor_delivery.py`, `tests/test_agent_monitor_manager.py`, `backend/gui_test/tests/test_shared_connector_control.py`, `tests/e2e/shared-control.spec.ts`다. 별도 담당자의 `tests/test_agent_monitor_lifecycle.py`와 기존 script/package/source/shared-settings 시험도 최종 묶음에서 실행했다.

검토로 발견한 문제를 해당 구현 담당자가 수정한 뒤 다음 경계를 확인했다.

- active Host 잠금, 영속 RUNNING/UNKNOWN 작업·예약, 원래 Runner identity가 공통 장비 설정 적용을 차단한다. 서버 revision만 저장한 상태는 APPLIED가 아니며 실제 Host 시작 설정 hash·board mapping이 일치해야 한다. 허용된 `node:null`도 소유자의 Board 정규화 결과와 비교한다.
- Qt 실제 편집/저장·revision 충돌·폴링·Linux 서버 경로 선택, 저장 응답 대기 중 추가 편집, 공통 revision 변경 없는 장비 적용 상태 변경과 공통 분석 응답 표시를 확인했다. GUI 종료가 mock 연결 수명을 끊지 않는다.
- React 공통 설정 저장에 기대 revision을 한 번 전달하며 충돌·후속 polling·탭 이동이 미저장 입력을 덮어쓰지 않는다. 이미지 BAT와 TC 폴더를 Linux 서버에서 구분 선택하며 TC Python 파일이 installer에 들어가지 않는다. 첫 실패 분석 대기 표시와 일반 재개 차단을 확인했다.
- 실제 전체 소스를 별도 폴더로 내보내 원본 저장소 없이 API/커넥터 모듈을 import하고 mock 설정을 저장했다. 복사한 API만 독립 runtime/port에서 띄워 정적 UI·공통 설정·managed instance/release/runtime health 식별자를 확인했다. 이 시험은 Worker를 시작하지 않으며 degraded/worker 미준비를 정상 서비스 준비 완료로 표시하지 않는다.
- 전달 checksum·release hash·소스 의존성 누락·symlink/traversal·runtime/log/개인 환경/생성 `.build` 제외, manager 설치 실패 시 기존 pointer/runtime 보존·정상 환경 재사용·작업 중 갱신 보류·서비스 잠금/상태 식별과 종료 보류를 검증했다. 설치·supervisor 시험의 프로세스/패키지 설치는 mock이다.

| 최종 실행 | 결과 | 로컬 전용 로그 |
|---|---|---|
| `bash scripts/build-ui.sh all --skip-install` (Node 22.23.4) | **PASS**, Dashboard/standalone 모두 typecheck·Vite build 성공 | `.local-reports/20261114-final-agent-monitor-validation/build-ui.log` |
| `python -m pytest tests/test_build_entrypoint.py tests/test_setup_commands.py tests/test_setup_runtime.py tests/test_runner_ports.py tests/test_windows_runner_bundle.py tests/test_editable_runner_build.py tests/test_gui_test_layout.py tests/test_gui_source_portability.py tests/test_agent_monitor_delivery.py tests/test_agent_monitor_manager.py tests/test_agent_monitor_lifecycle.py backend/gui_test/tests/test_package.py backend/gui_test/tests/test_shared_control.py backend/gui_test/tests/test_shared_connector_control.py -q` | **338 PASS / 15 SKIP**, 종료 0 | `.local-reports/20261114-final-agent-monitor-validation/pytest.log` |
| `npx playwright test shared-control.spec.ts --reporter=list --output=<고유 결과 폴더>` (격리 API, Worker 없음) | **5 PASS**, 종료 0 | `.local-reports/20261114-final-agent-monitor-validation/playwright.log` |

브라우저는 고정 npm lock과 맞는 Playwright Chromium 156을 `.local-reports/playwright-browsers/`에 설치해 실행했다. `PLAYWRIGHT_BROWSERS_PATH`와 기존 Node 22 경로를 해당 명령에만 지정했다. 최초 bundled browser 누락, system Chrome 157에서의 action 지연·timeout, 시험 fixture 보완 및 실제 결함의 초기 실패 로그/trace는 `.local-reports/20261114-shared-browser-01`~`06`, `20261114-shared-connector-tests-01`~`03`, `20261114-agent-monitor-tests-01`~`04`에 보존했다. 버전 일치 브라우저로 정상 클릭·입력·저장·탐색을 수행한 최종 결과와 구분한다.

기존 Git non-repository 대소문자 차이에 따른 source portability 실패 2건은 명시적인 non-repository 진단만 대소문자를 정규화하도록 수정되어 최종 source 시험에서 통과했다. Mac process identity 제약이 있던 `test_editable_runner_runtime.py`의 기존 광역 실패는 위 초기 근거에 보존하며 이번 14파일 최종 묶음에 포함하지 않았다. Windows 전용 15 SKIP, 실제 Windows CMD/PowerShell·Python 3.13·Z:/UNC·Linux service 운영·회사 TC/보드·SSH·LLM 인수는 이번 로컬 검증으로 완료 처리하지 않는다. 커밋·푸시·새 EXE 생성은 수행하지 않았다.

동시 작업 범위: `native_picker.py`, `web.py`, `web_actions.py`, `web_assets`, `BOARD_CONNECTOR_WEB_GUI_PLAN` 및 후속 connector web용 mjs/패키지 변경은 이 담당자의 구현·수용 시험 범위가 아니다. 해당 변경은 보존했다. 전체 소스 exporter에 파일이 포함되었거나 기존 package 회귀가 통과했다는 사실은 새 커넥터 web 화면의 기능 검증을 뜻하지 않는다. 이 기록의 UI 검증은 위 Qt 공통 설정과 Dashboard/standalone React 공통 설정·분석 표시 범위에 한한다.


최종 runtime 후속: run.sh와 설정 마법사의 Linux run이 같은 관리자를 호출하도록 통합했다. 기존 .runtime은 처음 연결한 경로로 고정하며 새 설치 위치로 조용히 옮기지 않는다. 과거 Wizard 소유 자식 종료 시험은 상주 관리자 위임/오류/메뉴 종료 독립 시험으로 교체했고 안전 종료 자체는 lifecycle 시험에서 검증한다. 최종153 PASS/11 SKIP, 로그 `.local-reports/plugin-centric-implementation-20261114/unified-runtime-retest.log`. 최초 이관 제한과 독립 추가 검토 APPROVED는 [전체 구현 기록](20261114-plugin-centric-implementation.md), [리뷰](20261114-plugin-centric-code-review.md)를 따른다.
