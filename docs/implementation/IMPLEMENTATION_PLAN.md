# 단계별 구현 지시

2026-11-06 RQ-55/D-59 간소화 후속: 단일 Test 설정 바깥 접기와 카테고리 콤보박스를 `TestPage.tsx`에 공통 구현한다. 기본 연결·반복 선택과 상세 입력을 분리하고 SourceSettings의 저장값 초기 선택, 조회 제한시간 프리셋/직접 입력, 현재 소스 상세, 명령 직접 편집 접기를 추가한다. 가시성만 바꾸어 전역/지역의 같은 draft·저장 범위·실행 게이트를 보존한다. API/DB/외부 실행 변경은 없다. 양쪽 진입·카테고리/접기 입력 보존·기본값·오류 표시·375px·기존 소스/명령/Suite/보기 모드 회귀와 두 UI 빌드로 검증한다.

2026-11-06 RQ-56/D-60 후속: 서버 소스 관리와 normal/live API 계약·Runner 스냅샷 전달을 먼저 정의하고 GUI의 `SourceSettings.tsx`를 단일 공유 편집기로 연결한다. 입력→확인→발견 ref 선택→버전 확인 적용을 구현하며 비 Git 폴더와 Git 커밋 트리를 구분한다. 적용 성공은 반환 카탈로그 교체·선택/반복/Suite/Preflight 초기화를 원자적으로 표시하고 명령 draft·과거 Run을 유지한다. legacy/분리된 default/live를 보존하며 Runner 미연결/구버전의 실행 차단과 소스 준비 상태를 분리한다. Suite 저장에는 현재 source_revision을 포함한다. API·카탈로그·실제 실행의 고정 기준 일치, 버전/오래된 응답 거부, 오류·미연결, 관련 탭 동기화·375px 및 기존 GUI 회귀를 별도 작성/실행/독립 리뷰하고 [설정·소스 실행 기록](../testing/runs/20261106-settings-sync.md)에 증거를 남긴다. 개발 중 실제 원격 Git·모델·장비·Jira 호출은 포함하지 않는다.

2026-11-06 RQ-55/D-59: `apps/web/src/main.tsx`의 단일 BSP 폼을 환경 설정/대시보드/Jira에서 유지하며 그룹 가시성만 변경한다. `packages/gui-test-ui/src/SettingsSection.tsx`에서 입력 트리를 유지하는 접근 가능한 접기를 공유하고 전역 접기 토큰·브라우저 상태 저장·오류 그룹 열기를 연결한다. 단일 `TestPage.tsx`를 지연 생성 후 유지하여 환경 설정에는 GUI 설정만 표시하고 TC 목록은 Test 현황에서 편집하며 브라우저 모드·명령 draft·Suite·반복 상태를 보존한다. 숨겨진 탭의 초기 조회/폴링/heartbeat는 취소한다. BSP/GUI/브라우저 저장 범위를 설명하고 375px 스타일을 보완한다. API·DB·기존 job/Run snapshot과 실제 외부 실행은 변경하지 않는다. T-169~175 및 기존 탭·입력 보호·모듈 선택·단독 GUI 회귀, 두 빌드와 분리된 독립 리뷰의 증거는 [설정 동기화 기록](../testing/runs/20261106-settings-sync.md)에 남긴다. 구현자의 문법 점검과 별도 실행자의 시험 결과를 구분한다.

2026-11-04 P3/RQ-20/39 후속: D-54의 탭 소개 정리, 이름 헤더의 ＋/−, 진행률 아래 실행 조작과 상시 세션·결과·로그를 같은 UI 변경 단위로 구현한다. API/DB/게이트는 유지하며 T-161 및 기존 GUI 회귀, 두 빌드와 분리된 Sol 리뷰를 [화면 정리 기록](../testing/runs/20261104-test-results-cleanup.md)에 남긴다.

2026-11-05 추가 범위: RQ-52/D-55는 TC 원본 Git 메타데이터의 읽기 전용 조회와 스냅샷 구분 표시다. RQ-53/D-56은 서버 device_test 문맥의 모듈별 TC 선택기·읽기 전용 조회·선택 문맥의 Preflight/Start 재검증·자동 목록 UI를 한 단위로 추가한다. 기존 수동 기본값·자동 프로파일 소유·실행 게이트와 일반 Run 호환을 보존하고 T-162/163 및 영향을 받는 계약·GUI 회귀를 별도 실행한다. 실제 Runner/보드 인수와 로컬 시험을 구분한다.

## 회사 전달 시 공통 산출물

DEV-PORT-01: 회사 전달 대상 기능을 구현·검증한 후 [이식 절차](../porting/README.md)에 따라 기능별 PORT 안내서를 작성한다. 고정 코드 커밋·선행 변경·재사용 코드·회사 조정 접점·시험 명령·미검증 범위를 연결한다. 회사판 구조와 적용 상태는 회사 담당자가 회사 저장소에 기록한다. 기존 P0~P7/O1~O5 제품 구현·인수 상태는 이 전달 절차로 변경하지 않는다.

P0~P7은 1차 로컬 구현/부분 검증이 진행됐으며 현재 상태는 [진행 기록](WORK_STATUS.md)을 따른다. 아래는 목표 단계이고 전체 완료를 뜻하지 않는다. 기존 코드를 보존·확장한다. 2026-11-06 D-58에 따라 O1~O4는 **IMPLEMENTED / LOCAL_MOCK_VALIDATED**, O5는 실제 외부 인수 미완료다. [현재 실행 기록](../testing/runs/20261106-orchestration-v2.md)을 따른다. 별도 M0 수동 Claude 패키지는 아래와 같이 구현했다.

```text
apps/web/                  화면, API client, 접근성·UI 시험
backend/domain/            게이트, 상태, 진행률, 유효성, 도구 선택
backend/api/               명령·조회·인증·수동 결과 API
backend/storage/           repository, migration, transaction, outbox
backend/worker/            scheduler, lease, reconcile, cancellation
backend/adapters/          agents/, build/, jira/, manual_test/
contracts/                 OpenAPI, result schema, fixture schema
tests/                     unit/, contract/, integration/, e2e/, regression/
config/examples/           비밀 값 없는 설정 예시
docs/                      요구사항·설계·기록
```

| 단계 | 구현 내용·변경 위치 | 종료 조건·검증 |
|---|---|---|
| P0 환경·설계 확정 | 실제 저장소 상태, Linux/Windows 버전, 도구 기능, 경로·빌드·시험·Jira 설정 양식. ADR-01~03 검증/채택. WORK_STATUS 갱신 | 미확인 항목을 가짜 값으로 채우지 않음. 호출/재개 지원 여부와 모의·실제 시험 경계 확정 |
| P1 도메인·저장 | domain, storage, migrations, contracts. ID·상태·게이트·입력 유효성·진행률·계획 버전 | T-01~18, T-35~38, T-47~50 중 단위/저장 시험. 실패/역순/중복 상황 통과 |
| P2 명령·실행 관리 | api, worker, fake adapters. command/outbox, 공유 자원 잠금, 재시작, 취소, UNKNOWN 복구 | T-03, T-13~18, T-40~43. 장애 주입으로 중복 writer가 없음을 검증 |
| P3 화면 | web, fixture API. 종합 진행도, 모듈 표, 상세·명령·설정·검토·수동 양식 | T-35~39, T-44~46. 모의 화면임을 명시. 버튼/오류/키보드/재연결 확인 |
| P4 Linux·도구 연동 | agents/build adapters, capability probe, 역할 템플릿. 실제 인증/세션/결과 수집 | T-01~02, T-19~25. 허용된 시험 프로젝트에서 실행. 설치 진술과 live 확인 구분 |
| P5 수동 시험·산출물 | manifest/download/upload, manual validator, 결과 무효화 | T-26~30, T-47~50. 가짜 fixture 시험과 실제 보드 결과 구분 |
| P6 Jira | direct/MCP adapters, discovery/probe, outbox, decision sync | T-31~34, T-51~54. mock 후 지정 환경 읽기 점검; 실제 생성 시험은 승인된 시험 범위에서 수행 |
| P7 통합·인수 | E2E, migration/restore, regression suite, 운영 안내 | T-55~60 및 필수 기존 시험. 실제 환경 미검증 항목은 BLOCKED/NOT_RUN 유지 |

각 단계 종료는 범위 내 필수 시험 통과, 증거 저장, 문서 일치, 차단 결함 없음으로 판정한다. 표에 언급한 시험은 대표 연결이며 전체 목록의 requirement/level을 기준으로 필요한 시험을 선택한다. 단계가 끝났다는 이유로 아직 실행하지 않은 live 시험까지 통과 처리하지 않는다.

## 매 단계 제출할 것

변경 파일, 연결 RQ/T ID, DB 변경 유무, 실제 실행한 시험과 evidence, 실패와 해결/미해결 내역, 외부 연동 확인 범위, 다음 단계. 구현 전 존재하지 않는 실행 명령을 README에 동작하는 명령처럼 적지 않는다. 테스트 러너를 도입하면 정확한 명령과 버전을 TEST_PLAN에 추가한다.

## 실제 환경에서만 확인할 입력

Linux 주소·계정·작업/원본/결과 경로, OS/도구 버전·재개 지원, 빌드 초기화/명령/출력, 실제 모듈과 선행 그룹, 보드와 필수 시험, 이미지 구성, Jira 프로젝트/필드/권한/MCP 기능. 설정 없이도 도메인·API·화면 fixture 작업은 진행 가능하다. 실제 연동이 필요한 단계에서만 필요한 입력을 모아 확인한다.

## 오케스트레이터 확장 — O1~O4 로컬 구현·모의 검증 완료 / O5 미인수

현재 구조는 React → FastAPI/SQLite → 단일 실행 worker → native CLI 또는 기존 JSON bridge다. opt-in 경로에 영속 모듈 보고/후보/보류, 별도 이벤트 조정 큐와 서버 제안 검증을 추가했다. 아래 표는 완료 조건이며 모두 통과했다는 뜻은 아니다. [오케스트레이터 명세](../design/ORCHESTRATOR_SPEC.md)와 [모듈 보고 계약](../design/AGENT_STATUS_CONTRACT.md)을 읽고 진행한다.

| 단계 | 수정/추가 대상과 작업 | 검증·완료 조건 |
|---|---|---|
| O1 계약·정규화 | contracts/의 조정 요청/응답·모듈 v2 JSON Schema와 fixture 신규 추가, backend/adapters/bridge.py 및 settings.py의 계약 버전/capability 확장. 역할별 details·보고 해시·제안 data 스키마 확정 | T-71, T-77/78/83. v1 정상 경로 유지, unsupported 버전·잘못된 필드 거부. 자동 적용은 schema 확정 후 |
| O2 영속 기록·게이트 | backend/storage/store.py와 migrations 추가, domain에 보고/후보/범위 보류/조정 제안 검증 추가. 결과+후보+보류의 원자 저장, 유일 ID·내용 해시·기준 버전 검사 | T-73~75, T-79/80/82. 기존 jobs/commands/events/artifacts 보존. backup/restore·중복/오래된 결과 시험 |
| O3 조정 실행 | backend/worker에 별도 조정 큐/호출 이력, adapter에 신규 orchestrate 분기. 결과 저장 후 trigger, job별 하나, 기존 worker만 실제 실행. 실패 해석·설정 한도·중지/UNKNOWN 처리 | T-72/76/81/82. 조정 timeout이 결과 수집/독립 모듈을 막지 않음. 프로세스 재시작 구간별 중복 실행 없음 |
| O4 화면·설정·판단 연결 | backend/api/main.py, apps/web/src에 조정 상태·제안·대기/거부 이유·보고 상세·한도 설정 추가. proposal 선택을 기존 command로 연결. Jira 후보 중복 방지 경로 결합 | T-79/80/84. 사람 판단/수동시험/최종 검토 유지, 일반 실패를 자동 Jira로 전송하지 않음. 설정은 새 job에 적용 |
| O5 외부 wrapper·인수 | 외부 에이전트 프로젝트에 두 전용 명세 인계, 실제 설치 CLI/모델/세션 기능 점검. 분석/수정/리뷰/빌드 결과 계약을 환경에 맞게 연결 | T-85 및 관련 기존 회귀. mock → 허용된 Linux 시험 프로젝트 → 수동 장비/Jira 시험 범위로 구분. 미실행을 PASS 처리하지 않음 |

DB 변경: 조정 트리거/호출/제안, AgentReport, DecisionCandidate, ScopeHold 및 receipt/lane 저장과 유일 제약을 BSP schema2에 추가했다. 실제 SQL은 store.py이며 이전·복구 시험의 최종 결과는 별도 기록한다. 논리 모델은 [DATA_MODEL.md](../design/DATA_MODEL.md)에 있다. M0 수동 패키지는 DB·기존 worker 실행 코드·설정 파일을 변경하지 않는다.

충돌 가능성: 현재 worker의 동기 coordinate/question 호출이 긴 조정을 막는 문제, 기본 단계 자동 배정과 proposal 적용의 이중 실행, source/plan 변경 중 오래된 결과, 조정·질문 세션 경합, v1 wrapper의 미지원 필드 묵살, code와 review의 결과 ID 혼동, 후보 접수 직전 후속 배정 경쟁. 각 단계의 시험으로 해결한 뒤 다음 단계로 진행한다.

도입 시 기존 job은 저장된 프로필과 계약 버전으로 유지한다. 현재 지원 설정은 [도입 안내](../agents/ORCHESTRATION_V2_OPERATIONS.md)를 따른다. 모르는 필드는 계속 거부한다. module_report_version=1·orchestration.enabled=false가 기본이며 새 job 생성 시 capability를 고정한다. 새 기능의 시작 조건은 양측 계약 지원 확인과 기존/신규 회귀 통과이며 이전 코드 전체 교체나 운영 데이터 초기화로 해결하지 않는다.

## M0 · 수동 Claude 에이전트 패키지

D-40 / RQ-35. 실제 agent 정의, 표준 라이브러리 검증 CLI, 예시 JSON/근거, 독립 폴더 내보내기, 사용 안내와 패키지 시험을 구현했다. O1~O5의 서버 계약 확정·DB·자동 실행·UI·실제 wrapper 인수는 포함하지 않는다. [진행 기록](WORK_STATUS.md)과 [새 실행 기록](../testing/runs/20261012-claude-agent-package.md)을 따른다. 실제 Claude 실행은 사용자가 진행한다.


## N1 · 작업 폴더 기반 내장 연결

D-42 / RQ-37. settings/native/process/bridge/worker/engine/API/설정 UI를 확장한다. DB 테이블 변경 없이 기존 JSON 프로필·작업을 보존하고 내장 경로를 기본으로 사용한다. 검증은 T-96 호환 → T-97 탐지 → T-98 계약/권한 → T-99 명령/산출물 → T-100 게이트·교차 리뷰·복구 → T-101 UI → T-102 실제 Linux 인수 순서다. T-102는 사용자의 실제 실행 증거 전 NOT_RUN이다. 자동 조정 O1~O5와 보고 v2는 범위에 포함하지 않는다.

## P3 후속 · GUI Test 사용성

D-44 / RQ-39: 공통 UI의 설정 접기 → TC 폴더/선택 표현 정돈 → 드래그 순서 편집과 Preflight 무효화 → 두 빌드 및 격리 Windows Mock 브라우저 검증. DB/API/worker 변경 없음. 2026-10-26 T-109~111 및 단독 브라우저 5개를 검증했다. [실행 기록](../testing/runs/20261026-gui-ux.md)의 파일 해시가 기준이며, 실제 Linux 통합/장비 인수를 완료한 단계로 확장하지 않는다.

### 2026-11-01 후속 구현 단위 · RQ-39 / D-45

TC 트리 및 목록 내 순서 편집 → 설정/검색 패널 접기·너비 → 단일 실패 TC 재실행 → Attempt 모델 사용량 저장/진행 표시 → 로컬 검증·8766 재시작. SQLite 테이블 이전 없음(optional JSON fields). 실제 모델·장비 연동은 별도이며 [이번 실행 기록](../testing/runs/20261101-tc-workspace.md)을 따른다.

### 2026-11-01 D-46 구현 단위

설정 탭/복귀 경로 및 소스·Suite 이동 → 반복 요청 검증/고정 실행 plan/slot별 복구·집계 → TC/전체 횟수 UI와 Suite 저장 → 32px 행/탐색기형 정렬 → GUI core/API·두 빌드·Chrome Mock 검증. optional JSON 필드만 추가하며 기존 plan 없는 Run의 복구를 유지한다. [실행 기록](../testing/runs/20261101-repeat-settings.md).

## GUI Test Windows 빌드

RQ-44: 독립 웹 빌드 → Windows 실행 스크립트 → GUI 전용 ZIP → PowerShell 5.1/7 CI와 오프라인 설치 검증. 사용자 가이드는 [Windows 빌드](../gui_test/WINDOWS_BUILD.md), 검증 범위는 T-119~121에 기록한다.

## 2026-11-03 D-47 구현 단위

RQ-39/44: scripts 빌드 진입점과 TC 전체 선택 → RQ-46: Windows 실행기/소스 snapshot/중복·종료 계약 → Linux adapter·capabilities·공통 UI → 별도 Astra 구현 리뷰 → 별도 GPT-6-sol 자동 시험 → 주 작업자의 수정/재시험. 실제 Linux·공유 폴더·보드 인수는 사용자 수행이며 T-130 NOT_RUN으로 남긴다. 자동 Job 동기화의 실환경 증빙은 후속 단위다.

## F1 자동 이미지 퓨징·TC · RQ-47

현재 단위: backend/worker/hardware.py, backend/gui_test/execution/flashing.py와 공통 Host/ProcessTree 연결, BSP stage 상태 UI, manifest 생성기 및 비활성 설정 예제. DB JSON 확장과 기존 lease 사용. T-131~135 모의 검증과 별도 Astra 리뷰 후 반영하고 실제 환경 T-136은 사용자 인수로 구분한다. [계약](../design/AUTOMATIC_FLASH_TEST.md), [진행 기록](WORK_STATUS.md).

## S1 실제 연결 마법사 · RQ-48

입력/원자 저장/보호된 토큰 → 설치·빌드와 프로세스 관리 → 이미지/manifest 메뉴 → 독립 Astra 리뷰 → 별도 GPT-6-sol 모의 시험과 Windows/Linux CI → 사용 안내/실행 기록/머지·게시. 변경 파일은 scripts/setup* 및 시험·문서이며 기존 API·DB 스키마·장비 실행 계약은 유지한다. 실제 환경 T-141은 사용자 인수다.


## RQ-49 실제 연결 보기

기존 manager/worker 보존 → 미설정 실제 조회/API → 화면 전환·빈 목록·상태·실행 차단 → 독립 Astra 리뷰와 GPT-6-sol 시험 → 문서/결과/머지·게시. DB schema 변경과 실제 장비 실행 없음.

## V1 · 다이어그램 탭 · RQ-50 · 로컬 구현·검증 완료

후속: 원본 구현·시험 커밋 `199b04b5c080e41ec9794326828fbc4874cef633`으로 전달 기준 고정을 마쳤다. 아래 구현 종료 당시의 미커밋 기록은 이력이며, 회사 적용/ACON 인수만 별도로 남는다.

문서 리뷰 후 사용자가 구현을 승인했다. [설계](../design/WORKFLOW_DIAGRAM.md)와 [PORT-001](../porting/PORT-001.md)을 기준으로 전용 폴더·호스트 조회 보호·새 탭을 구현하고 로컬 검증한다. 실제 ACON/회사 인수는 별도다.

구현 지시 후 예정 순서: 화면 데이터 형식과 ACON 연결 근거 확인 → workflow_diagram의 adapter/fixture와 상태 변환 → 독립 화면·접기/펼치기·모션 → main.tsx 탭/상태 연결 및 필요한 빌드 설정 → T-144~148 로컬 검증 → 실제 코드 커밋과 이식 안내 갱신. 데이터 변경은 현재 계획상 없음, ACON 실연결 T-149는 별도다. 기존 6단계를 화면 5단계로 표시하는 방안은 빌드 상태를 보존하도록 구현 시 구체화한다.

후속 리뷰를 반영한 구현 단위(1~4 로컬 완료, 5의 정식 전달 커밋/회사 인수는 후속):

1. 기존 snapshot의 실행/유효성/게이트/진행률을 좁힌 화면 모델과 순수 adapter로 변환하고 T-145 fixture를 먼저 고정한다. ACON 미지원은 확인 불가로 처리해 기본 화면 구현과 분리한다.
2. 기존 refresh에 조회 성공 관찰·초기 상태·events 실패 분리·선택 세대/버전 보호·중복 조회 병합이 필요한 범위를 확인하고 T-146으로 검증한다. 별도 fetch 루프를 추가하지 않는다.
3. 연결 점/실행 배지·경로 의미·접기/펼치기·모션을 연결하고 T-144/147을 검증한다. 현재 작업의 표시 상태만 메모리에 유지한다.
4. 격리 호스트/기존 통합·GUI 빌드와 T-148을 수행한다. 착수 시 시험 장비·응답시간 예산을 정하고 100개 모듈의 렌더/DOM/요청 수를 기록한다. CSS·SVG id·React 단일 인스턴스와 시험 도구 의존성을 확인한다.
5. 고정 코드/시험 커밋과 실제 의존성·호스트 변경·실행 명령을 PORT-001에 기록한다. 회사 구조/ACON 인수와 기존 N/A 목표 정책 차이는 미확인/별도 검토로 남긴다.

최종 로컬 결과: 전용 폴더/호스트 통합, 독립 Sol High 코드 리뷰 APPROVED, Luna Low 실행 32 PASS, 기존 두 빌드와 격리 production 빌드 PASS. 실제 파일 SHA256과 호스트 patch를 PORT-001에 연결했다. [실행 기록](../testing/runs/20261103-workflow-diagram-implementation.md)을 따르며 원본 고정 기능 커밋과 회사 T-149는 아직 없다.

2026-11-04 V1 UI 후속 완료: 오른쪽 단계 펼침·Archify 참고 dark 스타일·RUNNING 진입 이동 화살촉. 독립 리뷰 APPROVED, 두 빌드 및 전체 재시험 33 PASS. [실행 기록](../testing/runs/20261104-workflow-diagram-rightward.md)에 초기 환경 실패와 최종 증거를 보존했다. 호스트/데이터 접점 추가 없음. 후속 커밋 고정 및 실제 회사 인수는 별도다.

2026-11-04 추가 UI 후속 완료: 컴팩트 배치·배율 제어·영역 집중과 창 크기/탭 왕복 보존. 독립 리뷰 APPROVED, 전체36 PASS·두 빌드 PASS. [최신 기록](../testing/runs/20261104-workflow-diagram-zoom.md). 실제 회사 인수는 별도다.

## P1 Windows Runner 포터블 ZIP · RQ-51/D-53

현재 GUI Test 소스 경로·단독 빌드는 RQ-54의 [구조 계약](../design/GUI_TEST_LAYOUT.md)을 따른다. 과거 구현 단위의 명령과 결과는 당시 기록이다.

요구사항 분석 → 구조 설계 → 상세 설계 → 고정 버전으로 Windows x64 EXE 구현 → 별도 시험 작성 → 독립 실행·보고와 코드 리뷰 → 발견사항 수정/재시험 → ZIP·SHA256·회사 이식 안내 제공. 구현 범위는 Runner 패키징과 설정 진입점, frozen 자식 격리·외부 Python 환경 경계다. API/DB schema와 장비 자동 실행 정책은 유지한다. 기존 설정/DPAPI/runtime·UNKNOWN 재사용 및 저장소 밖 실제 EXE 기동을 T-156~159로 검증하며 실제 회사/SSH/보드 T-160는 NOT_RUN으로 구분한다.

## L1 GUI Test 구조 분리 · RQ-54/D-57

이동 전 작업 트리 manifest/복사본 확보 → 앱·Python·공유 UI 경계와 source/install namespace 확정 → 세 경로 이동·import/빌드/CI 경로 갱신 → launch의 정적 자산 주입 → 독립 ZIP·wheel staging → 별도 시험 작성·실행 → 새로운 Astra 최종 독립 코드 리뷰 → 발견사항 수정·재시험·기록 순서다. 기존 RQ-52/53/D-54 및 사용자 미커밋 변경을 보존한다. DB migration이나 데이터 재생성은 없다.

변경 위치는 `apps/gui-test/`, `backend/gui_test/`, `packages/gui-test-ui/src/`와 기존 Dashboard·worker·scripts·CI·시험의 연결부다. 소스 실행은 `python apps/gui-test/launch.py start`, Windows 단독 빌드는 `apps/gui-test/build.ps1`이다. `apps/web`·Git 없이 세 경로 묶음만으로 빌드·Mock 실행·설치 wheel을 검증한다. [구조 설계](../design/GUI_TEST_LAYOUT.md), T-164~168과 [실행 기록](../testing/runs/20261105-gui-test-layout.md)을 따른다. 실제 외부 호출과 운영 baseline 갱신은 포함하지 않는다.

## DEVPORT02 · GUI 호스트 이식·UI 동일성 · RQ-57/D-61

공통 Python 역참조 제거·host factory 주입 → public UI index/host adapter·스타일 격리 → fail-fast package target/manifest/독립 문서 → 별도 시험 작성 → 독립 코드 리뷰·별도 실행 보고 → 발견사항 수정·재시험 순서다. 현재 코드 단계이며 리뷰/시험은 대기다. T-183~190과 [실행 기록](../testing/runs/20261106-portability.md), [PORT-004](../porting/PORT-004.md)를 따른다. 기존 RQ-55/56 미커밋 변경과 승인된 배포 ZIP을 보존하며 실제 회사·외부 서비스·보드 실행은 하지 않는다. 검증된 raw/gzip 7쌍만 중복 raw 정리한다.

## RQ-60 · BSP 플러그인 연동

최초 요청은 문서만 대상이었고 당시 DESIGN_ONLY / IMPLEMENTATION_NOT_STARTED였다. 후속 지시로 문서 수정·검토 완료와 컨텍스트 압축 후 구현이 승인되었다. [설계](../design/BSP_UPGRADE_PLUGIN_INTEGRATION.md), [요청서](../agents/BSP_UPGRADE_PLUGIN_REQUEST.md), [PORT-007 계획](../porting/PORT-007.md).

후속 단계: 로컬 구현 커밋 `1a18ea6fab8b1caead3935ce70cb1e30153d631b`, 독립 코드 리뷰 APPROVED, T-200~207 모의 PASS, 최종 패키지 빌드와 Windows Runner smoke PASS. T-208은 Linux 설치·복원 미실행으로 NOT_RUN이고 T-209 회사 인수는 별도다. [검증 기록](../testing/runs/20261107-bsp-upgrade-integration.md).

## RQ-61 · 편집 가능한 Windows Runner

[계획](../design/EDITABLE_WINDOWS_RUNNER_PLAN.md)에 따라 오프라인 편집 배포, 빌드·재포장과 로컬 포트 처리를 구현했다. 최종 코드 `b42cacd1c110fd3ed0bd4898de51a3ccc3274b99`, 독립 리뷰 APPROVED, T-210~216 로컬 PASS다. T-217 회사 인수는 NOT_RUN이다. [PORT-008](../porting/PORT-008.md), [검증 기록](../testing/runs/20261107-editable-windows-runner.md)에 실패와 수정 이력을 보존한다.
## RQ-62 · Windows Runner 설정 편의

`scripts/setup_flashing.py`의 경로·serial 읽기 전용 탐색과 공통 콘솔 입력 → T-218~220 모의/회귀 → PORT-008·실행 안내 갱신 단위로 진행한다. 실행기/HTTP/SQLite schema와 외부 의존성은 변경하지 않는다. 웹 재빌드와 Runner 소스 갱신을 구분하며 실제 Windows·장비 확인 T-221은 별도다. [검증 기록](../testing/runs/20261112-runner-setup.md).

## RQ-64 · 연결 토큰 제거

공통 HTTP 경계와 클라이언트 → 설정 마법사·플래싱 설정 → 계약·가이드·PORT → T-230 로컬 회귀 순으로 구현한다. DB 이전·새 의존성은 없다. 실제 SSH/장비 인수 T-231은 별도다. 대시보드 자동 설치는 계속 보류한다. [검증 기록](../testing/runs/20261113-tokenless-connections.md).

## RQ-65 · Windows 설치·실행 단일화

준비 코드/설치 직렬화·환경 검증 → 단일 CMD와 중복 3개 제거 → 로컬/Windows wrapper 회귀 → 가이드·PORT → 사용자 승인된 main 게시 순으로 진행한다. DB·새 의존성 변경은 없다. [실행 기록](../testing/runs/20261113-connector-launcher.md).
