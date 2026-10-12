# API·명령·외부 연동 계약

경로와 필드는 구현 기준안이다. 실제 OpenAPI 명세와 어댑터 계약 시험은 구현 단계에서 생성한다. 클라이언트는 DB를 직접 읽지 않는다.

외부 BSP 에이전트의 실제 입력·출력은 [에이전트 상태·결과 보고 계약](AGENT_STATUS_CONTRACT.md)에서 단독 관리한다. 아래 HTTP API는 화면/운영 명령용이며 현재 에이전트 상태 push API가 아니다. 에이전트 결과는 worker의 내장 CLI 정규화 또는 기존 wrapper의 stdin/stdout JSON으로 받는다.

## 공통 요청 규칙

현재 단일 운영자 모드에서는 접속 키/세션 없이 로컬 연결을 허용한다. 변경 요청은 비밀 값이 아닌 `X-BSP-Client: dashboard` 헤더와 `Idempotency-Key`, 현재 `expected_version`을 전달한다. UI가 자동으로 헤더를 추가하며 사용자 입력은 없다. 같은 키+같은 내용은 기존 접수 결과를 반환하고 같은 키+다른 내용은 409. 서버는 권한·입력·게이트를 재검사한다. command 접수 202는 실행 성공이 아니다.

응답 예: `{command_id, status: "ACCEPTED", job_id, state_version}`. 오류는 `{code, message, field_errors, blocking_work_ids, correlation_id}`. 비밀 값과 원시 인증 오류를 응답에 노출하지 않는다.

| API 기준안 | 목적·핵심 입력 | 판정 |
|---|---|---|
| POST /api/v1/jobs | profile_revision, source refs, requested_scope, mode | 사전 점검 후 job/Start 명령 생성 |
| GET /api/v1/jobs/{id} | 상태 snapshot | state_version, last_observed_at, 진행률 근거 포함 |
| GET /api/v1/jobs/{id}/events?after= | 이벤트 재연결 | 누락 범위 보관 종료면 snapshot 재조회 안내 |
| POST /api/v1/jobs/{id}/plan-confirmations | plan_version, expected_version | 필수 분석·계획 내용 확인. 오래된 버전 거부 |
| POST /api/v1/work-items/{id}/retries | previous_attempt_id, reason | 게이트·실행 종료 확인 후 새 attempt |
| POST /api/v1/jobs/{id}/commands | target, intent, prompt, expected_version | 명령 분류 후 허용 동작만 실행 |
| POST /api/v1/attempts/{id}/cancel | reason | 중지 요청만 접수, 실제 종료 별도 확인 |
| POST /api/v1/jobs/{id}/pause | reason | 신규 배정 중지; 실행 중 작업 상태 보존 |
| POST /api/v1/jobs/{id}/resume | expected_version | 기존 job·세션·명령 재사용, 게이트 재평가 |
| POST /api/v1/manual-tests | attempt_id, board, bundle, cases, evidence | 현재 입력과 필수 결과 검증. 수동 시험만 등록 |
| GET /api/v1/artifacts/{id}/download | artifact_id | 사용자 권한과 실제 파일 해시 확인 |
| GET/POST /api/v1/connections | 설정 목록/등록 | 비밀 값은 별도 credential store 참조 |
| POST /api/v1/connections/{id}/probe | scope | 비파괴 조회로 인증·기능 확인. 티켓 생성 금지 |
| GET /api/v1/claude-environments/{id}/mcp | 실제 host/account/project | 등록 목록과 probe 상태 분리 |
| GET /api/v1/jobs/{id}/decisions | 내부/Jira 연결 목록 | 의존 작업·결정/반영 상태 함께 표시 |
| POST /api/v1/decisions/{id}/resolution | 선택·근거·기대 버전 | 결정 저장, 필요한 구현·검증은 별도 작업 |
| POST /api/v1/jobs/{id}/final-review | 기준 버전·결과·근거 | 필수 통합 검증과 추적성 확인 후 최종 완료 |

400 형식 오류, 401/403 인증·권한, 404 범위 내 대상 없음, 409 상태/버전/중복 충돌, 422 유효하지 않은 결과, 503 연결 불가를 구분한다. 재시도 가능 여부와 내부 추적 ID를 제공한다.

## Linux 연결

호스트 키 검증을 유지하는 SSH 연결을 사용한다. 비밀번호를 프롬프트로 받지 않고 키/인증 참조를 설정한다. 서버 서비스는 지정 계정으로, 등록된 프로젝트 경로에서 실행한다. 로그인 터미널과 비대화형 실행 환경 차이를 probe한다. PATH·환경 초기화·도구 버전·cwd·결과 디렉터리 쓰기 권한을 확인한다.

에이전트 호출은 실행 파일과 인자 배열/검증된 프로필로 구성한다. 내장 빌드/검증/통합은 사용자가 등록한 셸 명령을 Bash에서 실행한다. prompt, 모듈명, 경로를 셸 문자열에 이어붙이지 않는다. 심볼릭 링크 해석 후 허용 경로 안인지 검사한다. Windows 접속 종료와 Linux 작업 종료를 연결하지 않는다.

## 수동 시험 계약

사용자 필수 입력은 모든 필수 case의 PASS/FAIL뿐이다. API는 module_id, attempt_id, cases와 명령 키/expected_version을 전달한다. 보드·수행자·performed_at·evidence_id·sha256 직접 입력은 선택이다. 서버가 현재 artifact_id/sha256, source_revision, test_plan_version, fingerprint, submitted_at을 기록한다. 수행 시각 미입력은 null이며 등록 시각과 혼동하지 않는다. 선택값을 입력하면 시간대·파일 소유 범위·해시/기준 일치를 검증한다. 미입력만으로 완료를 거부하지 않는다.

오입력 수정은 새 submission revision으로 남긴다. 모든 필수 사례 PASS이고 현재 기준과 일치하면 자동 완료한다. 실패/누락은 보정할 수 있고 새 판단이 필요한 경우만 Decision을 만든다. 다운로드와 시험 제출은 별도 감사 이벤트다. 자동 플래시는 초기 구현하지 않는다.

## Jira 직접 연결

URL, 실제 배포 형태/버전, 프로젝트, issue type, 필수 필드 매핑, 인증 참조, 결정 필드, 상태 매핑을 설정한다. 사내 Jira를 Cloud라고 가정하지 않는다. 저장 시 형식 검사, probe 시 실제 접근 및 필요한 read/search/create/update capability를 확인한다. 쓰기 권한 확인이 비파괴적으로 불가능하면 미확인으로 표시하고 실제 생성 시 검증한다.

## Claude MCP 연결

지정 Linux 호스트·계정·프로젝트의 Claude 환경에서 목록을 얻는다. 이 대화를 실행하는 Codex의 MCP 목록으로 대신하지 않는다. 이름, 범위, 등록 상태, 확인 상태, 기능, 최근 점검 시각을 표시한다. 목록 조회가 실제 CLI/API에서 지원되지 않으면 수동 등록 프로필을 제공하고 “자동 검색 미지원”을 명시한다. 도구 이름은 실제 발견 결과로 매핑한다.

MCP는 전송 방식일 뿐 Jira 도메인 의미는 동일하다. 등록됨≠연결됨≠생성 가능. 연결 설정이 바뀌어도 기존 Job의 connection_revision은 조용히 교체하지 않는다.

## Jira 중복·동기화

새 판단을 내부 Decision으로 먼저 저장하고 같은 트랜잭션의 outbox로 생성 intent를 남긴다. internal decision ID를 외부 검색 가능한 필드/표식에 넣는 방식을 환경에 맞춰 검증한다. 응답 유실 시 기존 이슈 검색 후 연결한다. 신뢰할 검색 방법이 없으면 UNKNOWN 유지와 수동 연결을 제공하며 무조건 재생성하지 않는다.

선택한 어댑터 하나로 동기화한다. remote version/update 시각과 local expected_version으로 역순 덮어쓰기를 방지한다. Jira Done은 판단 완료 후보이며 결정 내용·반영 커밋·재검증을 충족해야 의존 작업이 해제된다. 연결 장애 때 outbox에 보존하고 독립 작업은 계속한다.

## 1차 구현에서 사용하는 실제 경로

기존 표는 목표 설계다. 현재 변경 명령은 `POST /api/v1/jobs/{job_id}/actions/{action}` 하나에 `{expected_version, data}`와 `Idempotency-Key`를 전달한다. action은 confirm/retry/manual-test/demo-complete-module/decision/resolve/apply-decision/prompt/pause/resume/final-review 등이다.

`demo-complete-module`의 data는 module_id, plan_version, fingerprint다. 서버에 고정된 작업 실행 방식과 그룹·게이트를 검사하며 클라이언트의 execution 값으로 우회할 수 없다. 현재 데모 attempt를 대체한 뒤 새 manual-demo attempt를 남긴다. 늦은 토큰의 결과는 무시한다. 설정은 `/api/v1/config`, 근거 업로드는 `/api/v1/jobs/{id}/evidence`, 다운로드는 `/api/v1/jobs/{id}/artifacts/{artifact_id}`다. 실제 구현은 `backend/api/main.py`를 기준으로 확인한다.

## 로그인 없는 로컬 진입 (D-38)

API와 화면은 loopback peer에서만 제공한다. serve.py는 127.0.0.1에 bind하며 forwarded 헤더로 peer를 바꾸지 않는다. API는 Host/Origin/Sec-Fetch-Site와 변경 요청 헤더를 검사해 외부 사이트·폼 요청을 거부한다. 일반 브라우저 진입/새로고침과 같은 출처 산출물 다운로드에는 별도 키가 필요 없다. `/api/v1/session`은 제거했으며 과거 access-token 파일/세션 쿠키는 사용하지 않는다. `/api/v1/health`의 instance_id는 시험 서버 식별자이며 인증 자격증명이 아니다.

## 오케스트레이터 확장과 모듈 보고 — 목표, 미구현

- 조정 호출과 proposal의 단일 계약은 [오케스트레이터 명세](ORCHESTRATOR_SPEC.md), 모듈 결과는 [보고 계약](AGENT_STATUS_CONTRACT.md)의 v1/v2 구분을 따른다. 모듈 wrapper의 결과는 worker가 받으며 agent가 HTTP API에 임의 상태를 POST하지 않는다.
- 현재 coordinate는 연결/복구, question은 읽기 전용 질문이다. 신규 orchestrate는 계획/재시도/전환/판단/검증 제안을 반환하는 별도 역할이다. worker가 설치된 wrapper의 capability를 확인하고 job별 지원 계약을 고정한 뒤 호출한다.
- 조정 입력은 영속 snapshot과 근거 참조이며 출력은 제안이다. 모델은 API URL·셸 문자열을 지정하지 않는다. 서버가 허용 제안을 기존 명령 처리와 연결하고 같은 버전/게이트/중복 검사로 적용한다.
- 화면용 확장에는 조정 상태·제안 목록 조회, 사용자 재검토 요청, 적용 대기 제안 선택, 제안/보고 근거 조회가 필요하다. 정확한 HTTP 경로/OpenAPI는 O4에서 구현하며 현재 존재하는 경로로 설명하지 않는다.
- 신규 판단 후보 접수는 결과 저장 및 blocking 후보의 영향 보류와 원자 처리한다. 참고용 후보는 배정을 막지 않는다. 조정 검토 후 내부 Decision을 먼저 생성/연결하고 현재 Jira 어댑터 경로를 사용한다. 운영자가 직접 판단을 등록하는 경로도 유지한다. 다른 프로젝트 agent의 직접 Jira 전송은 중복 경로가 되므로 사용하지 않는다.
- 현재 설정 모델은 미등록 필드를 거부한다. 오케스트레이터 명세의 새 설정은 구현 전 settings JSON에 추가하지 않는다. 도구/모델/호출 한도는 서버와 wrapper 양쪽 검증 후 적용한다.

## 수동 Claude 패키지의 현재 범위

수동 Claude 패키지의 명령은 로컬 파일 검사/내보내기 CLI다. API endpoint나 wrapper capability를 추가하지 않는다. 반환된 orchestration_result를 현재 coordinate/module endpoint에 보내지 않는다. [사용 안내](../agents/CLAUDE_ORCHESTRATOR_GUIDE.md)를 따른다.

## 소스 기준/브리지 설정 기본값

`POST /api/v1/config/bridge-defaults`는 Profile을 받아 workspace 기준 추천 agents/build_argv를 반환한다. 설정 저장·파일 생성·외부 실행은 하지 않는다. 기존 config/probe는 빌드 포함 실행 파일별 MISSING/NOT_EXECUTABLE/FILE_READY를 구분하고, 유효한 실제 환경이면 소스 기준 미리보기를 반환한다. 빈 source_revision은 새 job 생성 트랜잭션에서 Git HEAD로 해석하고 작업별로 고정한다. 같은 시작 명령의 재전송은 소스를 다시 해석하기 전에 기존 결과를 반환한다. 자세한 설정은 [안내](../agents/ENVIRONMENT_AND_BRIDGES.md)를 따른다.


## D-42 내장 연결 설정과 상태

Profile에 runner/native 설정·tool_paths/disabled_tools/models·agent_instructions/role_instructions·build_command/build_env_script/artifact_path/verification_command/integration_command를 추가했다. config validate/save/export는 이 필드를 보존한다. config/probe는 native에서 설치 경로·필수 옵션·로컬 로그인 설정 상태를 반환한다. 실제 모델/빌드/로그인을 점검 요청으로 실행하지 않는다. 기존 config/bridge-defaults는 고급 호환 모드용으로 유지한다.

새 job은 탐지한 도구 경로·점검 결과·역할 지침 내용을 고정한다. 기존 job과 사용자 브리지는 변경하지 않는다. `POST /api/v1/jobs/{id}/actions/retry-session`은 종료된 FAILED 연결만 새 세션으로 재시도하고 이전 실패를 history로 보존한다. UNKNOWN/NEEDS_RECONCILIATION은 거부한다. 이 명령도 기존 idempotency/expected_version 검사를 사용한다. 실패 환경을 고친 뒤 사용자 버튼으로 실행한다.

호출·필드 의미는 [환경 안내](../agents/ENVIRONMENT_AND_BRIDGES.md), 결과 정규화는 [보고 계약 12절](AGENT_STATUS_CONTRACT.md#12-내장-cli와-v1-정규화--d-42-현재-구현)을 따른다. Jira MCP는 별도 어댑터로 유지하며 이번 CLI 연결이 사내 Jira 자동 탐지를 구현한 것은 아니다.
