# 플러그인 중심 실행·연동 구현 · 2026-11-14

기준 main `e4f53ca1ec288feb3eb1b9ccff8335a398ad321c`. **로컬 구현·모의 검증 완료**, 실제 회사 인수 NOT_RUN. RQ-67/D-71/T-240~246/REG-0085. 기존 설계 WIP와 동시 진행 중인 브라우저형 커넥터 작업을 보존했다. 커밋·푸시·새 EXE 생성·실제 보드/모델/Jira 실행은 하지 않았다.

## 승인과 리뷰

사용자가 별도 세션의 요구사항 리뷰 후 즉시 구현을 승인했다. 분석 후 원인 조치/실행 조건 확인 뒤 자동 재실행, 같은 원인 재발 시 중단과 프로젝트 전체 스크립트 중복 제거·역할 중심 명명을 확정했다.

로컬 설정 `model_reasoning_effort=high`를 기준으로 한 단계 높은 `xhigh`, 명시 모델 `gpt-6-astra`의 별도 요구사항 리뷰를 수행했다. 부모 세션의 실행 중 override는 확인할 수 없어 설정 기준과 구분한다. 최초 12개 문서 SHA는 `.local-reports/plugin-centric-implementation-20261114/review-input.json`에 있다. 초기 CHANGES_REQUESTED와 수정 뒤 APPROVED는 [요구사항 리뷰](20261114-plugin-centric-review.md)에 보존했다. 제품 작성은 이 검토 종료 뒤 시작했다.

[독립 코드 리뷰](20261114-plugin-centric-code-review.md)의 PC-C01~06을 수정하고 범위 한정 APPROVED를 받았다. 이후 Linux 시작 경로/기존 runtime 보존의 추가 검토도 APPROVED이며 독립89 PASS/11 SKIP·후속2 PASS를 같은 리뷰 기록에 보존했다. 코드 리뷰 대상에 회사 장비 인수나 별도 브라우저형 커넥터 WIP를 포함하지 않는다.

## 구현

- 새 Run은 fail-stop-analysis-v1이다. 실패 결과·후속 배정 latch·영속 분석 outbox를 한 트랜잭션으로 기록한다. lease/CAS·중복 제출·새 근거 revision을 확인하며 과거 Run의 정책/입력 snapshot은 보존한다.
- 분석 결과는 제안이다. 서버에 주입한 trusted verifier가 조치·종료·보드·입력·예약을 확인한 뒤 새 Attempt 또는 새 준비/자식 Run을 허용한다. 같은 원인 재발과 chain 자동 재시도3회에서 중단한다. UNKNOWN 근거 갱신·PREFLIGHT 복구도 latch를 우회하지 않는다.
- 공통 설정은 기존 documents와 timeout 저장소를 묶은 CAS 원본이다. JSON import/export·허용 서버 폴더 조회·600초 fallback을 제공한다. 기존 명시10초와 실행 중 snapshot은 유지한다. DB schema version 변경은 없다.
- Windows desired와 실제 적용을 분리한다. 같은 runner와 revision, 실제 Host 시작 설정·예약/UNKNOWN 상태로 확인한다. Qt·React의 저장 전 입력과 충돌을 보존하고 분석 상태를 표시한다.
- 전체 Agent Monitor 소스·고정 의존성·미리 빌드한 두 UI·계약 시험을 파일 manifest와 함께 복사한다. runtime/log/build 환경·비밀 파일은 전달 소스에서 제외한다. 설치 재사용·실패 보존·활성화 잠금·Worker 단일 소유·API만 복구·안전 종료를 제공한다.
- run.sh와 Linux 설정 마법사는 같은 관리자를 호출하며 기존 .runtime을 고정 연결한다. 메뉴/화면 종료는 서비스 종료가 아니다. 다른 runtime으로 조용히 전환하지 않는다.
- 중복 실행/진단 별칭과 폐기 EXE builder를 제거했다. build-ui, build-windows-package, build-connector-bundle, serve_monitor, manage_profile, test_dashboard_browser로 이름을 정리하고 호출부·CI·패키징·문서를 같이 수정했다. OS별 얇은 wrapper와 서로 다른 역할은 유지한다. [조사](20261114-script-audit.md), [상세 정리 기록](20261114-script-consolidation.md).

공개 진입점·설치 명령·회사 adapter 연결과 최초 runtime 이관 예외는 [운영 안내](../../agents/PLUGIN_CONTROL_API.md), 회사 변경 위치·전제/복구는 [PORT-007](../../porting/PORT-007.md)·[PORT-009](../../porting/PORT-009.md)에 있다.

## 검증 근거

환경: macOS, CPython3.11.7, Node22.23.4, 저장소 잠금 버전과 맞는 Playwright Chromium156. 기존 가상환경을 사용했다. 실제 새 Linux pip 설치/OS 서비스 운영, Windows3.13 실행, 회사 장비/SSH/ACON/모델은 이 시험에 포함하지 않는다. 아래 집합은 일부 겹치므로 합산하지 않는다.

| 범위 | 결과 | 로컬 전용 로그 |
|---|---|---|
| 핵심 실패/분석·기존 Run·명령·integration service/http/recovery/batch/snapshot/observer/transport/remote·삭제 | 238 PASS, exit0 | `.local-reports/plugin-centric-implementation-20261114/core-review-preflight-final-08.log` |
| 공통 설정·bootstrap·브라우저 scope·클라이언트·기존 tokenless/portability | 94 PASS, exit0 (후속 수정 전, 최종 아래 묶음에서도 재검증) | `.local-reports/plugin-centric-implementation-20261114/shared-final-regression2.log` |
| 스크립트·패키지·source portability·delivery/manager/lifecycle·공통 설정·Qt 14파일 | 338 PASS / 15 Windows SKIP, exit0 | `.local-reports/20261114-final-agent-monitor-validation/pytest.log` |
| 두 UI typecheck/Vite build | PASS, exit0 | `.local-reports/20261114-final-agent-monitor-validation/build-ui.log` |
| 브라우저 공통 설정 저장/충돌·dirty polling·탭 이동·Linux 경로·분석/재개 차단 | 5 PASS, exit0 | `.local-reports/20261114-final-agent-monitor-validation/playwright.log` |
| 독립 리뷰어 실행: core/shared/Qt/delivery/manager/lifecycle | 134 PASS, exit0; POSIX marker 후속18 PASS | `.local-reports/20261114-plugin-code-review-final/pytest.log` 및 같은 폴더 후속 로그 |
| 최종 Linux 단일 관리자/runtime 고정·기존 Wizard·설치/빌드 진입점 | 153 PASS / 11 Windows SKIP, exit0 | `.local-reports/plugin-centric-implementation-20261114/unified-runtime-retest.log` |

복사 검증은 원본 없는 별도 폴더에서 전체 소스 export·API/connector import·mock 설정 저장·실제 복사 API 기동·정적 UI·공통 설정 요청·managed identity를 확인했다. Worker는 시작하지 않았으며 health의 degraded/worker 미준비를 READY로 표현하지 않았다. 의존성 설치/서비스 수명은 가짜 installer/child 시험이고 실제 pip 설치나 실제 Worker 운영 성공 근거가 아니다.

최종 변경 파일 manifest는 `.local-reports/plugin-centric-implementation-20261114/final-source-and-tests.json`이다. TEST_RESULTS.csv의 workingtree SHA가 해당 code/test 파일 집합을 가리킨다. 동시 웹 커넥터 파일은 제외했고 일부 패키지 파일에 보존된 동시 asset mapping 변경은 별도 범위다.

## 초기 실패와 수정

- 초기 스크립트 시험은 제거한 별칭을 호출한2건과 환경3건에서 실패했다. 별칭 호출을 공통 setup 명령으로 바꾸고 Git non-repository 진단만 대소문자 정규화했다. Mac process identity1건은 별도 광역 시험의 환경 제약으로 보존하고 최종338에 포함하지 않았다.
- 초기 전체 backend는 599 PASS/공유 커넥터6 FAIL 후 로컬 killpg 권한 오류로 중단했다. 동시 수정 중의 Qt 실패를 수정하고 해당 파일·핵심 경로를 집중 재시험했다. 전체 backend 완료로 표기하지 않는다.
- Qt 비동기 응답/같은 공통 revision에서 장비 적용 상태 갱신, nullable board node 비교, React 탭 이동 draft 및 TC 파일의 BAT 오선택을 회귀 시험으로 수정했다.
- 전달 manifest.release 검증 누락과 runtime/log/build 경로 포함, API 장애 시 Worker 종료·미완료 데이터가 있는 버전 활성화 문제를 수정했다.
- PC-C01~06의 UNKNOWN/수동 pause/빈 runner/활성화/미지원 정책/PREFLIGHT 재실행 결함과 모의 재현은 코드 리뷰 기록에 남겼다.
- bundled browser 누락과 시스템 Chrome157 자동화 지연은 실패로 보존하고 lock과 맞는 Chromium156에서 다시 실행했다.
- 마지막 단일 runtime 시험은 이전 활성 pointer를 생성하지 않은 mock fixture1건이 실패했다. 실제 current.json을 가진 fixture로 수정한 뒤153 PASS/11 SKIP로 확인했다. manifest 생성의 기존 Python 선행 검사는 유지했다.

초기 로그는 `.local-reports/20261114-script-consolidation-*`, `20261114-shared-browser-*`, `20261114-shared-connector-tests-*`, `20261114-agent-monitor-tests-*`, `20261114-plugin-code-review-*` 및 이번 구현 폴더에 삭제 없이 보존한다.

## 남은 경계

T-246 NOT_RUN. 회사 분석기·신뢰된 조치 검증기·ACON/설치 hook은 현지 adapter가 필요하다. verifier가 없으면 HOLD이며 BSP module_context의 입력 변경 재실행도 호스트 acceptance 연결 전 HOLD다. Python 자체·OpenSSH·드라이버·회사 TC 패키지 자동 설치는 제공하지 않는다. 실제 회사 Linux/Windows3.13·Z:/UNC·보드 플래싱/TC·SSH·장시간 로그·갱신/복원은 별도 인수다.

관리 설치 이력 없이 미완료/UNKNOWN runtime을 처음 연결하면 INITIAL_RUNTIME_ADOPTION_BLOCKED다. 운영자가 원래/검증된 호환 소스에서 작업을 정리하기 전 자동 인계하지 않는다. 데이터 삭제·새 후보 직접 실행으로 우회하지 않는다.

별도 브라우저형 커넥터의 native_picker/web/web_actions/web_assets 및 관련 계획은 동시 작업으로 보존했고 이번 기능 승인·수용 시험 범위가 아니다. 기존 API/전체 소스 복사 시험을 그 화면의 기능 검증으로 간주하지 않는다.

최종 문서 검사 PASS: 상대 링크1411개·요구사항67개·시험246개, 오류0. `git diff --check` PASS. 승인·재시험 후 범위 내 제품/시험 파일 해시 변경0을 확인했다.
