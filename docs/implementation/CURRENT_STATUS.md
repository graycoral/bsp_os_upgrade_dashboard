# 현재 상태

## 2026-11-14 최신 · RQ-68/D-72

회사 접점을 제외한 잔여 기능을 구현했다. 기존 Worker의 분석 실행, BSP 모듈 재실행 조건 재수락, Linux/Windows 캐시 자동 정리, 공개 의존성 준비·runtime 검사/이관/롤백·release 정리, 공통 저장 공간 UI와 커넥터 로그/보드 설정 탭을 포함한다. 최종 로컬 Python **1009 PASS / 24 SKIP**, Chromium **13+6 PASS**, 두 UI 빌드 PASS. 별도 Astra/xhigh 코드 리뷰 APPROVED, 검토 범위 미해결 P1/P2 없음. [실행 근거](../testing/runs/20261114-remaining-implementation.md), [독립 리뷰 판정](../testing/runs/20261114-remaining-code-review.md), [사용·플러그인 안내](../agents/PLUGIN_CONTROL_API.md).

기본 분석은 진단 후 HOLD다. 회사 분석·검증 프로그램과 ACON 매핑, 실제 Windows/Linux 설치·SSH·장비 인수 T-256은 NOT_RUN이다. 미커밋 작업 트리이며 새 EXE·배포 ZIP·게시·사용자 runtime 정리는 수행하지 않았다. 아래는 이전 단계의 근거다.


## 2026-11-14 현재 작업 · RQ-67/D-71

플러그인 중심 공통 설정·600초 fallback·실패 latch/분석 outbox·검증 후 재실행·복사 가능한 전체 Agent Monitor 설치 관리·스크립트 중복/명명 정리를 구현했다. 요구사항 Astra/xhigh 리뷰 APPROVED. 코드 리뷰와 runtime 후속 리뷰 APPROVED, 최종 집중 회귀·브라우저·빌드 PASS이며 [최신 실행 기록](../testing/runs/20261114-plugin-centric-implementation.md)에 근거를 모은다. 실제 회사 분석/조치 adapter·ACON·Linux/Windows 장비 인수는 NOT_RUN이다. 미커밋 작업 트리이며 게시하지 않았다. 아래는 이전 확인 이력이다.


확인일: 2026-11-07. 확인 기준 커밋: `1cd6ce8` (이 문서 변경 전). 이 요약은 실행 증거를 대체하지 않는다.

| 영역 | 현재 상태와 근거 |
|---|---|
| 공통 BSP·조정 | 로컬 구현·모의 검증 단계. v1 기본, v2·조정은 새 job opt-in. [운영 안내](../agents/ORCHESTRATION_V2_OPERATIONS.md), [검증](../testing/runs/20261106-orchestration-v2.md) |
| GUI host·이식 | 로컬 검증 및 독립 리뷰 근거가 있다. 회사 인수 T-190은 NOT_RUN. [PORT-004](../porting/PORT-004.md), [병합 검증](../testing/runs/20261106-portability-merge.md) |
| BSP 플러그인 RQ-60 | 로컬 구현·모의 검증. T-208 Linux 설치·복원 및 T-209 회사 인수 NOT_RUN. [기록](../testing/runs/20261107-bsp-upgrade-integration.md) |
| TEST BOARD CONNECTOR RQ-61 | T-210~216 로컬 PASS, 회사 SSH·COM·장비 인수 T-217 NOT_RUN. [기록](../testing/runs/20261107-editable-windows-runner.md) |
| TEST BOARD CONNECTOR RQ-62 · 2026-11-12 후속 | 설정 경로/serial 자동 탐색·공통 입력 및 플러그인 안내; 집중 모의 62 PASS. 기존 회귀의 환경/시험 결함은 별도 기록. EXE ZIP·체크섬 제거·신규 EXE 생성 없음. 독립 리뷰 NOT_REVIEWED, 회사 T-221 NOT_RUN. [기록](../testing/runs/20261112-runner-setup.md) |
| 외부 인수 | 실제 Linux·모델·장비·사내 Jira 및 회사 환경 검증은 각 실행 증거가 필요하다. 운영 baseline은 [NONE](../testing/BASELINE.md). |

기능별 상태와 미완료는 해당 [PORT](../porting/README.md), [시험 결과](../testing/TEST_RESULTS.csv), [누적 진행 기록](WORK_STATUS.md)과 실행 기록을 확인한다. 과거 PASS를 현재 코드의 검증으로 재사용하지 않는다.

## 2026-11-12 보드 커넥터 GUI 후속

RQ-63/D-67: 독립 Qt GUI와 같은 Mac preview, 공통 registry/보드 자동 표시, RX 콘솔·중앙 오류 cursor를 소스 구현했다. 기존 timeout/영구 삭제 WIP와 연계하고 고정 snapshot/Run pin/배타를 보존한다. 로컬 모의·Qt·브라우저 검증을 마쳤으며 [실행 기록](../testing/runs/20261112-board-connector-gui.md)을 따른다. 회사 T-228 NOT_RUN, 새 EXE/전달 ZIP 없음. 후속 사용자 지시로 커밋·게시를 진행하며 고정 대상은 PORT-009를 따른다. [PORT-009](../porting/PORT-009.md).

최종 근거: 광역605 PASS/간헐적 Mac killpg 1 FAIL 후 관련 집중53 PASS, 브라우저13 PASS, 양 UI build PASS. 전체 단일 실행 PASS나 실제 Windows/회사 통과로 표현하지 않는다. Astra는 [잔여 4건 코드 수정](../testing/runs/20261112-board-connector-code-review.md) 범위만 APPROVED다.

게시 전 재검증: 동일 광역 Python **606 PASS**, Chrome **13 PASS**, 양 UI build 및 최신 Qt 로그 4탭 검사 PASS. 이전 실패는 이력으로 보존하며 네이티브 앱 클릭 자동화는 도구 접근 거절로 BLOCKED다.

## 2026-11-13 · 경로 읽기 전용 표시

커넥터 연결 탭에 서버 선택/실행 원본과 Windows 작업 폴더 표시를 추가했다. 요청 전·이전 실행·단절을 구분한다. 경로 표시 제품 커밋은 `9fa5a0f88a8b26d333be3906cf3d63fa767d570d`이며 CI 복구 변경을 보존해 통합했다. RQ-63/T-229, [검증 기록](../testing/runs/20261113-board-connector-paths.md). 실제 Windows·회사 인수 NOT_RUN.

## 2026-11-13 연결 토큰 제거

RQ-64/D-68: Runner·등록·플러그인 공유 토큰 설정과 확인을 제거했다. SSH·loopback·실행 소유권은 유지한다. T-230 최종 집중 259 PASS / Windows 전용 10 SKIP. 광역 Mac 프로세스 identity 시험 제약과 최초 실패는 [실행 기록](../testing/runs/20261113-tokenless-connections.md)에 남겼다. 회사 T-231 NOT_RUN, 독립 리뷰 NOT_REVIEWED. 제품·시험 변경을 `929158f672a5a155d00b89ca679cf775ea3744b3`로 게시했다. 자동 설치 구현은 방향 재정리 요청에 따라 계속 보류한다.

## 2026-11-13 Windows 커넥터 설치·실행 단일화

RQ-65/D-69: 루트 `board-connector.cmd`로 최초 준비·조건부 설치·GUI 실행을 통일하고 중복 3개를 제거했다. 로컬 T-232 220 PASS / Windows 12 SKIP. Windows CMD·실제 최초 설치·오프라인 재사용 T-233 PASS. Windows 636 PASS/4 SKIP, Linux 1444 PASS/20 SKIP, 브라우저 60+18 PASS. 실제 회사 T-234 NOT_RUN. [실행 기록](../testing/runs/20261113-connector-launcher.md). 사용자 지시로 PR #20을 main `ad16eaac5c6837b85e73aea52864ce9b101170f1`에 병합·게시했다.

## 2026-11-13 · Python 3.13 호환

RQ-65/D-69/T-235/REG-0083: CMD와 준비 코드의 Python 3.13 지원·우선 선택, 다른 minor 환경 재사용 방지, 누락 소스 안내를 반영했다. 로컬 Python 3.11 회귀 64 PASS/Windows 5 SKIP, Windows CPython 3.13 wheel 해석·다운로드 PASS. 제품 `1447c207515f828dcf925075625b6f0f7c3a6d60`을 main에 병합했다. 실제 Windows 3.13.17 CI 644 PASS/4 SKIP·최초 설치/오프라인 재실행 PASS. Linux 1451 PASS/21 SKIP·브라우저 60+18 PASS. [실행 기록](../testing/runs/20261113-connector-python313.md). 회사 Z:·GUI·SSH·장비 T-234 NOT_RUN.

## 2026-11-13 · RQ-66 포트 멀티플렉서·GUI

물리 COM 단독 소유, TC 공통 Serial 어댑터 자동 제공, PuTTY Raw 조회/명시 수동 제어, 기존 FlashService·ConsoleObserver 내부 구독, 보드 선택과 변경분 GUI 렌더링을 구현했다. 기존 프로파일은 native 유지, 새 GUI 설정은 proxy 기본이다. DB·새 의존성 변경 없음. 사용자 구현·커밋·푸시 승인. [실행 기록](../testing/runs/20261113-connector-multiplexer.md)에 로컬/Windows CI와 회사 T-239 NOT_RUN을 구분한다. ADB USB 프록시와 실제 회사 적용은 이번 완료에 포함하지 않는다.

RQ-66 게시 후속: 제품 `dc2f855cf7e24638763bea7c2696673d4d407a02`을 PR #22로 main `e963c966b0c37f9e1d5ac8f6b8fdb1e0326f5980`에 병합했다. Windows Python 3.13 회귀 655 PASS/4 SKIP, 최초 설치·오프라인 재실행 PASS. Linux Python 1462 PASS/21 SKIP, 대시보드 브라우저 60 PASS와 standalone 브라우저 18 PASS. Windows 3.12 독립 빌드·오프라인 설치·실행은 PowerShell/pwsh 모두 PASS. 회사 UART·TC·SSH/PuTTY T-239는 NOT_RUN이다.

## 2026-11-14 · Agent Monitor 플러그인 중심 설계 협의

사용자는 운영 중심을 플러그인으로 옮기고 기능별 절차를 확인한 뒤 인터페이스를 하나씩 협의하도록 요청했다. 제품명 Agent Monitor, 설명 bsp-os-upgrade를 확정했다. [협의 문서](../design/PLUGIN_CENTRIC_INTERFACE_PLAN.md)에 확정 방향과 제안을 분리했으며 F01 서비스 준비·접속부터 사용자 확인 대기다. 코드·DB·설정 변경과 구현·게시 없음. 제품시험 NOT_RUN / 독립 리뷰 NOT_REVIEWED. [문서 작업 기록](../testing/runs/20261114-plugin-centric-design.md).

F01 후속: 사용자가 설치 후 최소 개입과 필요한 구성 요소·의존성의 일괄 자동 준비를 확정했다. [협의 문서](../design/PLUGIN_CENTRIC_INTERFACE_PLAN.md)에 반영하고 설치/준비/조회 인터페이스 제안을 추가했다. 플러그인 종료 시 작업 수명은 F01-Q2로 확인 대기다. 자동 설치의 구현·실제 실행은 아직 하지 않았다.

F01/F07 후속: 사용자가 플러그인 창 종료 후 TC 지속과 TC당 기본 600초를 확정했다. 제한시간은 플러그인·Agent Monitor·설정 파일에서 수정한다. [협의 문서](../design/PLUGIN_CENTRIC_INTERFACE_PLAN.md)에 현재 10초 fallback/DB 설정과의 차이, 보드 단절·무응답·종료 불명 구분을 기록했다. 같은 보드의 후속 TC 보류는 F07-Q1 제안으로 확인 대기다. 제품 코드는 변경하지 않았다.

F07-Q1 후속: 사용자는 TC 하나가 실패하면 나머지 TC를 수행하지 않고 플러그인에서 분석하도록 확정했다. 앞선 같은 보드 보류·사용자 상태 확인 후 재실행 제안을 대체한다. [협의 문서](../design/PLUGIN_CENTRIC_INTERFACE_PLAN.md)에 후속 배정 차단, 실패/콘솔 로그 전달, 플러그인 부재 시 분석 요청 보관 절차를 제안했다. 분석 후 재실행·재개 조건과 병렬 실행 영향은 미확정이다. 제품 코드·DB 변경 및 실제 분석 실행은 없다.

F03/F04/F06 후속: 사용자가 이미지 준비·전송·fastboot·BAT·재부팅 확인·TC의 전체 흐름과 플러그인 중심의 사람 개입 없는 진행을 확정했다. Agent Monitor·ACON·보드 커넥터 상호 연동 및 커넥터에서도 공통 설정 변경을 반영했다. [협의 문서](../design/PLUGIN_CENTRIC_INTERFACE_PLAN.md)에 단일 실행 배정, 설정 변경/적용 상태 공유, Linux/Windows 경로 구분을 제안했다. ACON 실제 접점·동시 수정/실행 중 적용·분석 후 재실행 조건은 상세 확인 대상이다. 문서만 변경했으며 제품 구현·실제 설치/장비 실행·게시 없음.

2026-11-14 전달 안내 후속: PORT-007/009에 플러그인 중심 변경 범위·기존 고정 코드와의 차이·새 코드 커밋 미정·시험 NOT_RUN을 반영했다. 플러그인 담당자의 진입 문서는 BSP_UPGRADE_PLUGIN_REQUEST이며 최신 읽기 순서와 설계 검토 요청문을 추가했다. 사용자 추가 지시로 전체 요구사항 완성 후 별도 세션에서 effort를 한 단계 높인 독립 리뷰와 지적 반영을 예정했다. 전체 리뷰는 아직 NOT_RUN / NOT_REVIEWED이며 제품 코드·DB·설정·게시 변경 없음.

코드 재사용 전달 후속: 사용자는 플러그인에서 코드를 그대로 복사해 사용할 수 있도록 요구했다. 기존 PluginClient의 core/httpx 의존성과 소스 내보내기/headless staging을 확인하고, 의존 소스·설치 진입점·시험 동봉 및 원본 저장소 없는 폴더에서의 독립 검증을 설계·PORT-007·플러그인 요청서에 완료 조건으로 추가했다. Agent Monitor의 플러그인 설치/관리 관계와 상주 서비스·Windows 커넥터의 별도 수명을 구분했다. 새 전달 검증 NOT_RUN, 제품 코드·배포물 변경 없음.


## 2026-11-14 · 보드 커넥터 웹 기본 화면·CMD 진단

사용자 지시에 따라 기본 진입을 browser로 전환하고 Qt는 `--ui qt` 호환 옵션으로 보존했다. 같은 Windows Manager/Host/COM 코어를 재사용하며 전용 브라우저 세션·CSRF·설정 revision/잠금·수집 시각 stale·Windows 경로 선택·공통 설정/로그 UI를 연결했다. CMD BC 진단/로컬 로그/Python override/읽기 전용 진단과 source/wheel/bundle 자산 연결을 포함한다. 새 DB 이전·커밋·게시·배포 ZIP 없음.

최신 통합 관련 회귀 241 PASS/20 Windows SKIP, Chromium 12 PASS. 첫 연속 조작 누락(REG-0087)과 Astra 리뷰 지적 네 건(REG-0088)을 수정해 재시험했다. 같은 폴더의 보드/로그 탭 추가도 보존하고 다중 COM 오류/ARIA 두 P2 delta를 보완해 Astra xhigh APPROVED를 받았다. storage/BC-29의 실제 동작은 이 GUI 승인 범위가 아니다. Astra xhigh는 web 단위 34건을 독립 PASS하고 최종 로그를 확인해 웹 기본 전환/수정 범위를 APPROVED했다. 사용량 제한 실패·CHANGES_REQUESTED 이력은 보존했다. 회사 CMD 원인(REG-0086)과 Z:/UNC·실제 Windows 파일 선택·SSH/COM/USB 인수 T-250 및 별도 public-tools 실제 설치는 NOT_RUN이다. 새 커밋·게시 없음. [시험·manifest](../testing/runs/20261114-connector-web.md), [리뷰 상태](../testing/runs/20261114-connector-web-review.md), [사용·오류 해결](../gui_test/TEST_BOARD_CONNECTOR_GUI.md), [회사 적용](../porting/PORT-009.md)을 따른다.
