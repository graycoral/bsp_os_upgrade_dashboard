# API·명령·외부 연동 계약

경로와 필드는 구현 기준안이다. 실제 OpenAPI 명세와 어댑터 계약 시험은 구현 단계에서 생성한다. 클라이언트는 DB를 직접 읽지 않는다.

## 공통 요청 규칙

변경 요청은 인증된 actor, `Idempotency-Key`, 현재 `expected_version`을 전달한다. 같은 키+같은 내용은 기존 접수 결과를 반환하고 같은 키+다른 내용은 409. 서버는 권한·입력·게이트를 재검사한다. command 접수 202는 실행 성공이 아니다.

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

명령은 실행 파일과 인자 배열/검증된 프로필로 구성한다. prompt, 모듈명, 경로를 셸 문자열에 이어붙이지 않는다. 심볼릭 링크 해석 후 허용 경로 안인지 검사한다. Windows 접속 종료와 Linux 작업 종료를 연결하지 않는다.

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
