# 단계별 구현 지시

P0~P7은 1차 로컬 구현/부분 검증이 진행됐으며 현재 상태는 [진행 기록](WORK_STATUS.md)을 따른다. 아래는 목표 단계이고 전체 완료를 뜻하지 않는다. 기존 코드를 보존·확장한다. 이번에 추가한 오케스트레이터 O1~O5는 **NOT_STARTED**이며 자동 연동 설계 상태다. 별도 M0 수동 Claude 패키지는 아래와 같이 구현했다.

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

## 오케스트레이터 확장 — O1~O5, 전부 NOT_STARTED

현재 구조: React 화면 → FastAPI/SQLite → 단일 worker → JSON wrapper. 제안 구조: 기존 실행 경로에 영속 모듈 보고/판단 후보 저장, 이벤트 기반 조정 호출, 서버의 제안 검증을 추가한다. [오케스트레이터 명세](../design/ORCHESTRATOR_SPEC.md)와 [모듈 보고 계약](../design/AGENT_STATUS_CONTRACT.md)을 읽고 진행한다.

| 단계 | 수정/추가 대상과 작업 | 검증·완료 조건 |
|---|---|---|
| O1 계약·정규화 | contracts/의 조정 요청/응답·모듈 v2 JSON Schema와 fixture 신규 추가, backend/adapters/bridge.py 및 settings.py의 계약 버전/capability 확장. 역할별 details·보고 해시·제안 data 스키마 확정 | T-71, T-77/78/83. v1 정상 경로 유지, unsupported 버전·잘못된 필드 거부. 자동 적용은 schema 확정 후 |
| O2 영속 기록·게이트 | backend/storage/store.py와 migrations 추가, domain에 보고/후보/범위 보류/조정 제안 검증 추가. 결과+후보+보류의 원자 저장, 유일 ID·내용 해시·기준 버전 검사 | T-73~75, T-79/80/82. 기존 jobs/commands/events/artifacts 보존. backup/restore·중복/오래된 결과 시험 |
| O3 조정 실행 | backend/worker에 별도 조정 큐/호출 이력, adapter에 신규 orchestrate 분기. 결과 저장 후 trigger, job별 하나, 기존 worker만 실제 실행. 실패 해석·설정 한도·중지/UNKNOWN 처리 | T-72/76/81/82. 조정 timeout이 결과 수집/독립 모듈을 막지 않음. 프로세스 재시작 구간별 중복 실행 없음 |
| O4 화면·설정·판단 연결 | backend/api/main.py, apps/web/src에 조정 상태·제안·대기/거부 이유·보고 상세·한도 설정 추가. proposal 선택을 기존 command로 연결. Jira 후보 중복 방지 경로 결합 | T-79/80/84. 사람 판단/수동시험/최종 검토 유지, 일반 실패를 자동 Jira로 전송하지 않음. 설정은 새 job에 적용 |
| O5 외부 wrapper·인수 | 외부 에이전트 프로젝트에 두 전용 명세 인계, 실제 설치 CLI/모델/세션 기능 점검. 분석/수정/리뷰/빌드 결과 계약을 환경에 맞게 연결 | T-85 및 관련 기존 회귀. mock → 허용된 Linux 시험 프로젝트 → 수동 장비/Jira 시험 범위로 구분. 미실행을 PASS 처리하지 않음 |

DB 변경: 조정 트리거/호출/제안, AgentReport, DecisionCandidate, ScopeHold의 저장과 유일 제약이 필요하다. 실제 테이블/인덱스는 O1/O2에서 확정한다. 논리 모델은 [DATA_MODEL.md](../design/DATA_MODEL.md)에 있다. M0 수동 패키지는 DB·기존 worker 실행 코드·설정 파일을 변경하지 않는다.

충돌 가능성: 현재 worker의 동기 coordinate/question 호출이 긴 조정을 막는 문제, 기본 단계 자동 배정과 proposal 적용의 이중 실행, source/plan 변경 중 오래된 결과, 조정·질문 세션 경합, v1 wrapper의 미지원 필드 묵살, code와 review의 결과 ID 혼동, 후보 접수 직전 후속 배정 경쟁. 각 단계의 시험으로 해결한 뒤 다음 단계로 진행한다.

도입 시 기존 job은 저장된 프로필과 계약 버전으로 유지한다. 현재 설정은 모르는 필드를 거부하므로 미래 설정 예시를 먼저 운영 JSON에 넣지 않는다. 새 기능의 시작 조건은 양측 계약 지원 확인과 기존/신규 회귀 통과이며 이전 코드 전체 교체나 운영 데이터 초기화로 해결하지 않는다.

## M0 · 수동 Claude 에이전트 패키지

D-40 / RQ-35. 실제 agent 정의, 표준 라이브러리 검증 CLI, 예시 JSON/근거, 독립 폴더 내보내기, 사용 안내와 패키지 시험을 구현했다. O1~O5의 서버 계약 확정·DB·자동 실행·UI·실제 wrapper 인수는 포함하지 않는다. [진행 기록](WORK_STATUS.md)과 [새 실행 기록](../testing/runs/20261012-claude-agent-package.md)을 따른다. 실제 Claude 실행은 사용자가 진행한다.


## N1 · 작업 폴더 기반 내장 연결

D-42 / RQ-37. settings/native/process/bridge/worker/engine/API/설정 UI를 확장한다. DB 테이블 변경 없이 기존 JSON 프로필·작업을 보존하고 내장 경로를 기본으로 사용한다. 검증은 T-96 호환 → T-97 탐지 → T-98 계약/권한 → T-99 명령/산출물 → T-100 게이트·교차 리뷰·복구 → T-101 UI → T-102 실제 Linux 인수 순서다. T-102는 사용자의 실제 실행 증거 전 NOT_RUN이다. 자동 조정 O1~O5와 보고 v2는 범위에 포함하지 않는다.

## P3 후속 · GUI Test 사용성

D-44 / RQ-39: 공통 UI의 설정 접기 → TC 폴더/선택 표현 정돈 → 드래그 순서 편집과 Preflight 무효화 → 두 빌드 및 격리 Windows Mock 브라우저 검증. DB/API/worker 변경 없음. 2026-10-26 T-109~111 및 단독 브라우저 5개를 검증했다. [실행 기록](../testing/runs/20261026-gui-ux.md)의 파일 해시가 기준이며, 실제 Linux 통합/장비 인수를 완료한 단계로 확장하지 않는다.
