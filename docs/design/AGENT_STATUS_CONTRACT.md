# 외부 BSP 에이전트 상태·결과 보고 계약

기준일: 2026-10-12 · 현재 전송 계약 v1 / 오케스트레이터 연동용 v2 설계 · 대상: 다른 저장소에서 개발한 모듈 에이전트와 CLI 연결 wrapper 작성자.

**외부 에이전트에 전달할 기준 문서는 이 파일이다.** 에이전트는 대시보드가 배정한 한 단계의 결과를 JSON으로 반환하고, 대시보드 worker가 검사·저장하여 화면 상태를 갱신한다. 기존 운영/역할 문서에 흩어진 입력·출력 필드 목록은 이 문서로 통합했다.

현재 구현은 **단계 종료 시 결과 1회 수신**이다. 에이전트가 실행 중 진행률을 계속 보내는 기능, heartbeat, 상태 파일 감시, 에이전트용 HTTP POST 수신은 아직 없다. **1~10절은 현재 v1, 11절은 미구현 v2 설계, 12절은 내장 CLI 적용 규칙**다. `demo`에서는 실제 외부 에이전트를 호출하지 않는다.

**내장 CLI 사용자는 2절과 12절을 먼저 읽는다.** 3절의 stdout 규칙과 기존 JSON 예시는 사용자 wrapper의 v1 계약이다. 내장 모델 호출에는 어댑터가 전달하는 결과 schema가 적용되며 native 필수/허용 필드는 12절이 우선한다.

오케스트레이터의 업무·권한·제안 계약은 [ORCHESTRATOR_SPEC.md](ORCHESTRATOR_SPEC.md)에서 관리한다. 모듈 agent는 worker에 보고하고, 서버가 저장한 동일 결과를 오케스트레이터와 대시보드가 읽는다. 오케스트레이터에게 직접 보고하는 별도 채널이나 두 번째 실행 배정자를 만들지 않는다.

| 계약 | 지원 상태 | 사용 시점 |
|---|---|---|
| 모듈 결과 v1 | 현재 구현 | 내장 CLI 정규화 또는 기존 wrapper. 단일 최종 결과 |
| 모듈 결과 v2 | DESIGNED / NOT_IMPLEMENTED | 서버·wrapper 양쪽 지원을 확인한 뒤 사용. 역할별 구조화 보고 추가 |
| 오케스트레이터 요청/결과 v1 | 별도 신규 계약, NOT_IMPLEMENTED | 조정 판단용 message_type. 모듈 v1이나 coordinate와 다른 계약 |

## 1. 누가 언제 상태를 갱신하는가

```text
사용자 Start → 서버가 작업·모듈·실행 기준 저장
  → worker가 게이트 확인, attempt 생성, RUNNING 기록
  → 내장 어댑터가 설치된 CLI 실행 또는 기존 JSON wrapper 호출
  → CLI 구조화 응답/이벤트를 단일 결과로 정리
  → 종료 시 worker에 v1 결과 반환
  → worker가 대상·근거·리뷰·산출물을 확인하고 결과/이력 저장
  → 화면이 서버 상태를 다시 읽어 현재 단계와 종합 진행도 표시
```

| 상황 | 갱신 책임 | 에이전트가 전달할 것 |
|---|---|---|
| 배정 대기·선행 대기·계획 확인 대기 | 서버 | 없음. 에이전트가 다음 단계를 임의 실행하지 않음 |
| 단계 실행 시작 | worker | 받은 요청의 식별자와 입력 기준을 보존 |
| 실행 중 | 현재는 worker의 `RUNNING` 상태 유지 | 중간 JSON을 stdout에 추가하지 않음 |
| 단계 성공 | 에이전트 결과 → 서버 검증 | `SUCCEEDED`, 구체적인 근거, 실행 식별자, 단계별 산출물 |
| 단계 실패 | 에이전트 결과 → 서버 검증 | `FAILED`, 실패 근거, 오류 분류, 해당하면 동일 원인 키 |
| 비정상 종료·시간 초과 | wrapper/worker | 가능한 경우 실패 결과. 프로세스 장애는 worker가 별도로 실패 처리 |
| 재시도·오래된 결과·취소·복구 | 서버 | 예전 결과를 새 attempt에 재사용하지 않음 |
| 수동 장비 시험 | 사람 → 서버 | 에이전트 보고 대상 아님. 필수 사례별 PASS/FAIL은 사람이 등록 |
| 모듈/전체 완료와 진행률 | 서버 | 전체 완료 상태나 퍼센트를 직접 쓰지 않음 |

화면은 현재 약 1.8초 간격으로 조회한다. 이는 에이전트 보고 주기가 아니다. 종합 진행도는 유효하게 완료한 필수 단위를 집계하며, 실행 중인 단계가 임의로 50%를 보고해 반영하는 방식이 아니다. 코드 작성 후 별도 리뷰가 끝나야 코드 단계 결과를 확정한다.

## 2. 외부 프로젝트 연결 방법

기본 `runner: native`에서는 Linux 작업 폴더·소스 위치·기존 에이전트 지침 폴더·프로젝트 빌드/시험 명령을 설정한다. 도구 탐지와 Claude/OpenCode/Codex 결과 변환은 대시보드가 담당한다. 별도 wrapper 작성이나 bridges 폴더는 필요하지 않다. 자세한 설정은 [환경 안내](../agents/ENVIRONMENT_AND_BRIDGES.md)를 따른다.

다른 프로젝트의 agent 정의는 역할 자료로 가져오며 자체 배정기를 실행하지 않는다. 모듈 목록은 서버가 고정한 ID로 관리한다. 새 작업마다 경로/도구 기능/역할 지침을 고정한다. 호스트/계정 입력만으로 SSH 원격 실행하지 않으며 API와 worker는 도구가 설치된 Linux에서 실행한다.

기존 wrapper가 있는 경우만 고급 설정 `runner: bridge`를 선택하고 `agents.claude/opencode/codex`, `build_argv`의 절대 실행 파일/인자 배열을 유지한다. 아래 3절의 단일 JSON stdout 규칙은 **기존 브리지의 전송 규칙**이며 내장 CLI의 원시 JSONL 스트림에 적용하지 않는다. worker가 받는 논리 결과 필드는 두 모드가 공유한다.

## 3. 기존 JSON 브리지 전송 규칙

- **입력:** UTF-8 JSON 객체 1개를 stdin에서 EOF까지 읽는다. 줄바꿈 1개를 기다리는 방식으로 읽지 않는다. 요청에 마지막 줄바꿈이 없을 수 있다.
- **출력:** 처리가 끝나면 stdout 전체가 UTF-8 JSON 객체 1개가 되게 출력한다. Markdown 코드 블록, 설명 문장, CLI banner, 복수 JSON, NDJSON 스트림을 섞지 않는다. 최대 1MiB다.
- **정상적인 실패 보고:** 작업이 실패했어도 구조화된 `FAILED` 결과를 반환할 수 있다면 wrapper 자체는 **exit 0**으로 종료한다. 내부 빌드 exit code 등은 `evidence`에 적는다.
- **wrapper 비정상 종료:** exit code가 0이 아니면 stdout 결과는 채택되지 않고 worker가 `ENVIRONMENT` 실패로 처리한다. 잘못된 JSON/객체가 아닌 JSON/초과 크기는 `CONTRACT` 실패다. 실행 파일 호출 자체의 오류도 현재 `CONTRACT`로 분류될 수 있다.
- **로그:** stdout은 결과 전용이다. stderr는 현재 worker가 영속 보관하거나 화면에 전달하지 않는다. 필요한 상세 보고서는 wrapper가 작업 폴더에 저장하고, `evidence`에 요약과 경로를 적는다. 경로를 적는 것만으로 첨부·다운로드가 등록되지는 않는다.
- **제한 시간:** 모듈 단계/리뷰/통합은 `timeout_seconds`(기본 900초, 설정 범위 10~14400초), 조정 세션 연결과 질문은 현재 각각 60초다. 시간 초과 시 worker가 POSIX 프로세스 그룹을 종료한다. wrapper가 별도 백그라운드 작업을 남기면 안 된다.
- **완료 시점:** 자식 에이전트·빌드·파일 쓰기가 실제 끝난 후 반환한다. 완료를 보고한 뒤 별도 프로세스가 코드를 계속 수정하면 안 된다.
- **상태 소유권:** 에이전트는 대시보드 DB, 잠금, attempt 상태, 계획·모듈 목록을 직접 수정하지 않는다. 대시보드 접속 키는 필요 없으며 에이전트 자체 서비스 인증은 별개다.

## 4. 대시보드가 보내는 모듈 실행 요청

대상 stage는 `analysis`, `design`, `code`, `build`, `verification`, `integration`이다. `review`는 7절의 별도 호출이며, `coordinate`와 `question`은 8절의 다른 형식이다.

| 필드 | 형식 | 의미와 처리 규칙 |
|---|---|---|
| `schema_version` | 정수 `1` | 지원하지 않는 버전은 추측하지 말고 실패 보고 |
| `job_id` | 문자열 | 업그레이드 작업 ID |
| `module_id` | 문자열, 통합은 `null` | 대상 모듈 ID. 이름으로 대체 금지 |
| `stage` | 위 단계 문자열 | 이번 호출에서 수행할 한 단계 |
| `attempt_id` | 문자열 | 이번 실행 ID. 재시도 때 새 값. 결과에 그대로 복사 |
| `session_id` | 문자열 | 대시보드가 부여한 역할 실행 세션 ID. 외부 CLI의 세션 ID와 다름 |
| `fingerprint` | 문자열 | 입력 기준 식별값. 직접 다시 계산하지 말고 결과에 그대로 복사 |
| `source_revision` | 문자열 | 모듈 코드 결과의 소스 기준이 있으면 그 값, 아니면 작업 시작 기준 |
| `module` | 객체 | 대상 모듈의 현재 snapshot. 이전 단계 결과·변경 추적·이력 등을 참고 |
| `model_policy` | 문자열 | `configured`, `opus` 또는 빌드 등에서 빈 문자열. wrapper가 실제 모델 설정에 대응 |
| `source_paths` | 객체 | `old_base`, `vendor_tree`, `new_base` 실제 소스 경로 |

`module`에는 현재 `id`, `name`, `group`, `changes`, `stages` 등이 들어온다. `stages`의 이전 결과를 이어서 사용하고 새 작업처럼 기존 수정을 덮어쓰지 않는다. 전체 내부 snapshot을 그대로 외부 로그에 출력하지 않는다. 향후 추가된 모르는 필드는 필요한 필드 외에는 무시해도 된다.

통합 호출은 `module_id: null`이고 `module`은 `{id: null, name: "전체 통합", stages: {}, modules: [...]}`다. 이때 `modules`로 전체 모듈 결과를 전달한다. 일반 모듈 호출과 달리 통합의 최상위 `source_revision`은 작업 시작 기준이므로, 실제 통합 대상은 각 코드 결과와 현재 작업 폴더까지 대조한다.

현재 요청 최상위에는 `work_item_id`, `plan_version`, `allowed_paths`, `output_directory`, `role` 필드가 없다. 논리 데이터 모델의 필드가 모두 전송된다고 가정하지 않는다. 필요한 작업 범위나 근거가 없으면 추측으로 실행하지 말고 실패 근거를 남긴다. 단계별 역할·쓰기 범위는 wrapper 설정과 [역할 지침](../roles/RUNTIME_ROLES.md)으로 제한한다.

## 5. 모듈 에이전트가 반환해야 하는 필드

`analysis/design/code/build/verification/integration`의 공통 결과다.

| 필드 | 보고 규칙 | 현재 처리 |
|---|---|---|
| `attempt_id` | **필수** 문자열. 받은 값 그대로 | 성공 응답의 요청 일치 여부 검사. 실패에도 항상 포함하도록 wrapper 작성 |
| `fingerprint` | **필수** 문자열. 받은 값 그대로 | 성공 응답의 입력 기준 일치 여부 검사. 소스 revision으로 대체 금지 |
| `outcome` | **필수** `SUCCEEDED` 또는 `FAILED` | 단계 완료 후보/실패. `PASS`, `DONE`, `RUNNING`, `BLOCKED`는 이 필드의 값이 아님 |
| `evidence` | **필수** 비어 있지 않은 문자열 | 단계 상세의 근거/오류 설명. 무엇을 수행했고 어떤 결과인지 사람이 이해할 수 있게 작성 |
| `source_revision` | 코드 성공 시 **연동 규칙상 필수**; 빌드/검증도 실제 대상 기준 명시 권장 | 리뷰 대상과 산출물 기준에 사용. 현재 구현은 누락 시 작업 시작 기준으로 대체하므로 누락에 의존하지 말 것 |
| `error_class` | 실패 시 **연동 규칙상 필수** | 실패 분류. 현재 파서는 생략도 받지만 원인 분류와 전환 정책을 위해 작성 |
| `cause_key` | `FIX` 실패이면 **필수** | 같은 수정 원인을 식별하는 안정적인 키. 같은 원인이면 재시도에도 같은 값 |
| `artifact` | 모듈 `build` 성공 시 **필수** | 6절의 파일 경로·SHA-256. 다른 단계에 넣어도 자동 파일 등록 없음 |
| `schema_version`, `job_id`, `module_id`, `stage` | 추적을 위해 받은 값 복사 권장 | 현재 결과 파서는 필수/일치를 검사하지 않음. 식별의 실제 기준은 worker 호출 및 attempt/fingerprint |

기존 브리지는 실패 응답 echo를 성공과 동일하게 검사하지 않는다. 내장 CLI는 성공/실패 모두 검사한다. 그렇더라도 wrapper는 성공/실패 모두 `attempt_id`와 `fingerprint`를 정확히 복사해야 한다. 결과를 재전송하는 API는 없으며, worker는 최신 attempt·실행 토큰·현재 입력 기준을 다시 검사하여 늦은 결과가 최신 상태를 덮어쓰지 못하게 한다.

`evidence`에는 수행 내용, 대상 파일/소스 기준, 확인 방법과 결과, 상세 보고서 위치를 적는다. 분석/설계처럼 시험을 실행하지 않은 경우 시험 PASS라고 적지 않는다. 비밀번호·토큰·인증 원문은 넣지 않는다. `summary`나 `evidence_refs`만 보내면 현재 필수 `evidence`를 대신할 수 없다.

다음 예시의 ID·fingerprint·revision은 설명용이다. 실제 요청값과 실제 수행 결과로 바꾼다.

```json
{
  "schema_version": 1,
  "job_id": "job-example",
  "module_id": "module-ethernet-example",
  "stage": "analysis",
  "attempt_id": "attempt-example-1",
  "fingerprint": "copy-the-request-fingerprint",
  "outcome": "SUCCEEDED",
  "evidence": "Ethernet 벤더 변경 3건을 신규 OS와 비교했다. 이식 후보 2건과 이미 반영된 1건의 근거는 reports/ethernet/analysis.md에 기록했다. 코드 수정과 장비 시험은 수행하지 않았다."
}
```

위 분석 보고의 분류는 현재 `evidence`로만 전달된다. 변경별 분류 자동 반영의 제약은 9절을 따른다.

```json
{
  "attempt_id": "attempt-example-2",
  "fingerprint": "copy-the-request-fingerprint",
  "outcome": "FAILED",
  "error_class": "FIX",
  "cause_key": "ethernet.rx-ring.api-mismatch",
  "evidence": "RX ring API 변경을 수정하고 같은 대상의 컴파일을 다시 실행했으나 동일 타입 오류로 실패했다(exit 2). 기존 수정은 보존했다. 시도 차이와 오류 위치: reports/ethernet/attempt-2.md."
}
```

| 오류 분류 | 사용 기준 |
|---|---|
| `FIX` | 실제 코드 수정 후 동일 기준으로 재검증했으나 수정 실패. 단순 첫 오류 발견·분석 실패·리뷰 지적을 횟수 늘리기 위해 분류하지 않음 |
| `ENVIRONMENT` | 인증·도구·네트워크·빌드 환경 문제 또는 시간 초과 |
| `CONTRACT` | 잘못된 입력·버전·결과 형식·식별자 불일치 |
| `ARTIFACT` | 필요한 이미지/파일 부재 또는 해시 불일치 |
| `DEPENDENCY` | 수행에 필요한 근거·의존 결과 부재 또는 실행 중 기준 변경 |
| `REVIEW` | 별도 리뷰 미통과/근거 부족. 일반적으로 서버가 코드 단계에서 부여 |

현재 원인 분류 문자열은 enum으로 엄격히 제한되지 않지만 위 표로 통일한다. 자동 Opus 전환은 **코드 단계 이력**의 `FAILED` + `error_class: "FIX"` + 동일 `cause_key`가 2회인 경우 다음 배정에서 적용한다. 타임스탬프·attempt ID를 cause_key에 붙이지 않는다. 결과에 `hard: true`를 추가해 조기 전환하는 수신 기능은 없다.

## 6. 단계별로 무엇을 보고해야 하는가

| `stage` | 현재 실행 경로 | `evidence`에 기록할 내용 | 추가 처리 |
|---|---|---|---|
| `analysis` | Claude 내장/기존 브리지 | 3개 소스 비교, 벤더 변경 목적·반영/이식/제외/판단 후보, 관련 파일·의존·필수 시험 | 분석만 수행. 코드 수정 금지 |
| `design` | Claude 내장/기존 브리지 | 수정 설계·대상 파일·인터페이스 영향·대안·검증 방법·판단 필요 사항 | 최초 계획 확인과 선행 게이트는 서버가 확인 |
| `code` | OpenCode 또는 대체 Claude 내장/기존 브리지 | 실제 수정·현재 revision/diff·수행 시험·남은 문제·이전 실패 대비 차이 | `source_revision` 보고. 성공 후 서버가 별도 리뷰 실행 |
| `build` | 내장 build_command / 기존 build_argv | 빌드 대상·소스 기준·명령/프로필·종료 코드·로그 위치 | 성공이면 `artifact.path`와 `artifact.sha256` 필수 |
| `verification` | 내장 verification_command / 기존 Claude 브리지 | 실제 수행/조회한 검증별 PASS/FAIL/NOT_RUN, 대상 이미지·소스, 실패 근거 | 내장은 등록된 검증 명령의 종료 결과, 기존 브리지는 실제 검증 도구를 연결 |
| `device_test` | 사람 | 이 프로토콜 호출 없음 | 사례별 PASS/FAIL만 필수, 나머지는 선택 입력 |
| `integration` | 내장 integration_command / 기존 build_argv | 전체 모듈 대상 통합 빌드·회귀 범위·결과·소스와 로그 위치 | 모듈과 별도 attempt. 현재 통합 artifact 자동 가져오기 없음 |

빌드 성공 예시:

```json
{
  "attempt_id": "attempt-build-example",
  "fingerprint": "copy-the-request-fingerprint",
  "outcome": "SUCCEEDED",
  "source_revision": "0123456789abcdef0123456789abcdef01234567",
  "evidence": "선행 그룹 검증 이미지 빌드 완료(exit 0). 대상 소스와 빌드 프로필 및 로그: reports/boot/build.md. 실제 장비 시험은 아직 수행하지 않았다.",
  "artifact": {
    "path": "out/boot-validation.img",
    "sha256": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
  }
}
```

예시 해시는 실제 해시가 아니다. `sha256`은 완성된 파일 bytes로 계산한 64자리 SHA-256 hex여야 한다. `path`는 `workspace` 안의 파일이며 상대 경로를 권장한다. 작업 폴더 밖 경로·심볼릭 링크 이탈·없는 파일·해시 불일치는 거부한다. 파일 쓰기를 마친 뒤 응답하고 worker가 가져오는 동안 덮어쓰지 않도록 attempt별 고유 경로를 사용한다.

worker가 파일을 runtime 저장소로 복사하고 ID·이름·크기·검증한 해시를 등록한다. **외부 agent가 artifact ID를 발급하지 않는다.** 현재 모듈 빌드는 파일 1개만 지원한다. 분석 보고서나 검증 로그는 경로를 `evidence`에 기재해도 자동 복사되지 않는다.

## 7. 코드 리뷰 결과 계약

코드 성공 결과 뒤 대시보드가 별도로 선택한 리뷰 도구를 호출한다. 일반 모듈 요청에서 다음 내용이 달라진다.

- `stage`는 `review`, `session_id`는 새 리뷰 세션 ID다.
- `implementation`에 작성 에이전트의 결과 객체 전체가 추가된다.
- `attempt_id`와 `fingerprint`는 코드 실행의 값을 유지한다. 별도 모듈 단계 attempt가 아니다.
- **리뷰할 revision은 `implementation.source_revision`을 우선한다.** 요청 최상위 `source_revision`은 작성 전 값일 수 있다. `model_policy`는 리뷰에서 configured로 재설정한다. 구현의 Opus 전환을 리뷰 도구 모델에 잘못 적용하지 않는다.

리뷰 도구는 `outcome: "SUCCEEDED"`와 비어 있지 않은 `evidence`로 통과를 보고하고, 수정 필요/검토 실패면 `FAILED`와 근거를 반환한다. echo 필드를 복사한다. 내장 리뷰는 성공/실패 모두 일치 검사하며 기존 브리지의 완화된 수신 경로는 호환 유지한다.

```json
{
  "attempt_id": "attempt-code-example",
  "fingerprint": "copy-the-request-fingerprint",
  "outcome": "SUCCEEDED",
  "evidence": "implementation.source_revision에 해당하는 변경과 diff를 검토했다. 벤더 변경 반영·인터페이스 호환성에 차단 항목 없음. 검토 범위와 근거: reports/ethernet/review.md. 장비 시험은 수행하지 않았다."
}
```

서버가 이 응답을 내부 `review.outcome: PASS/FAIL`로 바꾼다. **리뷰 wrapper의 최상위 outcome에 PASS/FAIL을 보내지 않는다.** 작성 에이전트가 자신의 결과에 `review: {outcome: "PASS"}`를 넣어도 별도 리뷰를 대체하지 못한다. 리뷰 과정에서 직접 코드를 고쳐 놓고 원래 revision을 승인해서도 안 된다.

## 8. 조정 세션과 질문은 별도 형식

### `coordinate` — 조정 세션 연결/복구

요청 필드: `schema_version: 1`, `stage: "coordinate"`, `job_id`, `session_id`, `resume_external_id`(최초에는 null), `modules`(전체 snapshot), `source_revision`, `analysis_only: true`.

이 호출에는 모듈용 `attempt_id`, `fingerprint`, `source_paths`가 없다. 정상 연결/복구 시 다음을 반환한다. `external_session_id`는 실제 CLI 세션 식별자여야 하며 내부 session_id를 임의로 복사해 연결 증거로 삼지 않는다.

```json
{
  "outcome": "SUCCEEDED",
  "external_session_id": "actual-external-cli-session-id",
  "evidence": "조정 전용 세션 연결 확인. 분석 전용으로 준비했으며 구현과 빌드는 시작하지 않았다."
}
```

실패는 `FAILED`와 실패 근거를 반환한다. 기존 세션 재개를 실제 확인하지 못했으면 복구 성공으로 보고하지 않는다. 이 결과에 모듈 제안을 추가해도 현재 모듈 목록을 자동 갱신하지 않는다.

### `question` — 화면의 상태·오류 질문

요청 필드: `schema_version: 1`, `stage: "question"`, `read_only: true`, `job_id`, `target`(모듈 ID 또는 `*`), `prompt`, `snapshot`(작업 전체 상태).

이 호출에도 최상위 attempt/session/fingerprint 필드는 없다. `outcome: "SUCCEEDED"`와 `evidence`에 답변을 반환한다. 답변 실패 시 `FAILED`와 이유를 반환한다. UI에 전달하는 답변은 현재 최대 8000자로 잘린다. 질문 응답을 위해 코드를 수정하거나 새 실행·Jira 전송을 하지 않는다.

## 9. 판단 요청과 현재 미지원 항목

새 판단이 필요하면 `evidence`에 **질문, 선택지, 영향 모듈, 권장안, 진행할 수 없는 작업**을 남긴다. 그 판단 없이는 배정된 단계를 완료할 수 없으면 `FAILED`와 적절한 오류 분류(예: `DEPENDENCY`)로 반환하고 성공을 주장하지 않는다. 독립 모듈의 결과는 정상 보고한다.

**현재 에이전트 결과에서 Decision/Jira를 자동 생성하는 수신 기능은 없다.** 운영자가 화면의 「새 판단 항목」으로 대상과 내용을 등록해야 의존 대기가 적용되고 설정된 Jira 연동으로 이어진다. `proposed_decisions`를 반환하는 것만으로 대기/티켓이 생성되지 않는다. 에이전트 자체가 별도 Jira를 전송하면 대시보드의 중복 방지와 상태 연결을 보장할 수 없으므로 이 경로를 사용한다. 향후 v2의 `decision_requests` 접수·영향 보류·오케스트레이터 검토는 11절과 오케스트레이터 명세를 따른다. 이 목표가 현재 동작을 바꾸지는 않는다.

| 항목 | 현재 상태 | 외부 에이전트 작성 시 주의 |
|---|---|---|
| 세부 `%`, 현재 세부 작업, heartbeat, 실시간 로그 | 미구현 | stdout 중간 이벤트 금지. `progress_percent` 등을 넣어도 화면 반영 없음 |
| HTTP 상태 push / 결과 파일 감시 | 미구현 | agent용 임의 URL이나 파일명을 가정하지 않음. `/events`는 화면이 읽는 서버 이벤트 |
| 변경별 분석 분류 자동 반영 | 미구현 | 현재 성공 분석은 기존 변경 항목을 `port_required`로 일괄 표시함. 상세 분류는 근거 보고서에 남기고 운영자 검토 필요 |
| `changed_files`, `evidence_refs`, `proposed_decisions`, 모듈 제안의 자동 반영 | 미구현 | 추가 JSON 필드가 저장될 수 있어도 별도 화면/게이트 동작 없음 |
| 세부 역할별 파일·경로 OS 격리 | 미구현 | wrapper의 허용 작업 범위와 실행 계정으로 제한. 요청에 존재하지 않는 allowed_paths를 추정하지 않음 |
| revision/diff의 실제 소스 일치 자동 증명 | 제한적 | revision 문자열만으로 실제 수정·리뷰를 보장하지 못함. wrapper가 소스·diff·시험 근거를 대조 |
| 실제 CLI 세션 복구·프로세스 재연결 | 환경별 미검증 | UNKNOWN 작업을 새 실행으로 중복 시작하지 않음 |

실시간 보고를 추가하려면 event ID/순번, attempt/fingerprint, 보고 시각, heartbeat 만료, 중복/역순 처리, 세부 진행률의 분모, 재연결 및 수신 경로를 먼저 확정하고 서버·wrapper·시험을 함께 변경해야 한다. 이 문서에 쓰인 설명만으로 해당 기능이 구현된 것은 아니다.

## 10. 외부 에이전트 인수 체크리스트

이 체크리스트는 **연결 대상 환경에서 새로 실행할 항목**이다. 대시보드 로컬 fixture 시험 통과로 실제 wrapper까지 PASS라고 간주하지 않는다.

- stdin EOF까지 요청 JSON을 받고 stdout에 결과 객체 하나만 반환한다.
- 성공/실패 모두 요청의 attempt_id/fingerprint를 보존한다. 재시도는 새 ID로 기록한다.
- evidence가 실제 수행 내용과 맞고, 실행하지 않은 시험·장비 작업을 완료로 보고하지 않는다.
- 코드의 실제 revision/diff가 리뷰 대상과 일치하고 별도 리뷰가 수행된다.
- 빌드 결과 파일이 workspace 안에 존재하고 전달 해시와 실제 bytes가 일치한다.
- FAILED + exit 0, 비정상 종료, 시간 초과, 잘못된 JSON, 오래된 결과를 각각 확인한다.
- 동일 코드 수정 원인만 FIX/cause_key로 누적하고, 환경 오류를 Opus 전환 횟수에 넣지 않는다.
- 최초 계획 확인·부트로더 전체 완료·공유 수정/빌드 잠금·사람의 수동 시험을 우회하지 않는다.
- 판단 필요 결과가 자동 Jira가 아님을 확인하고 운영자의 판단 등록 절차를 검증한다.
- 결과 기록에는 wrapper/도구 버전, 설정·소스 기준, 시험 시각, PASS/FAIL, 근거 위치를 남긴다. 실패 후 재시험은 과거 기록을 덮어쓰지 않는다.

## 구현과 문서의 기준 위치

- 요청/결과 JSON 처리와 코드 리뷰: [bridge.py](../../backend/adapters/bridge.py)
- 실행·산출물 가져오기·조정/질문: [worker/main.py](../../backend/worker/main.py)
- 상태 반영·재시도·수동 시험: [engine.py](../../backend/domain/engine.py)
- 도구 선택·진행도·게이트: [policy.py](../../backend/domain/policy.py)
- 설정 필드: [settings.py](../../backend/settings.py)

필드나 의미를 변경할 때 이 문서와 구현·계약 시험을 같은 변경에서 갱신한다. 다른 문서는 이 문서를 참조하고 별도 필드 목록을 복제하지 않는다. 독립 Claude 검토와 실제 외부 wrapper 인수는 아직 수행하지 않았다.

## 11. 오케스트레이터 연동용 모듈 보고 v2 — 미구현 설계

이 절은 외부 에이전트 개발자가 **앞으로 무엇을 추가해야 하는지** 정의한다. 코드에는 아직 v2 검증·정규화·판단 후보 접수가 없다. 기존 서버가 모르는 필드를 무시한다는 이유로 v2 호환이라고 판단하지 않는다. v2 도입은 [구현 계획 O1~O5](../implementation/IMPLEMENTATION_PLAN.md)와 계약 시험을 통과한 뒤 활성화한다.

### 11.1 배정과 보고 시점

1. 서버가 이번 호출의 요청 ID·입력 기준·예상 결과 ID를 발급하고 wrapper에 전달한다.
2. agent가 배정된 한 단계만 수행한다. 실행 중의 상태는 worker가 관리한다. 오케스트레이터에 진행 상태를 자연어로 별도 전송하지 않는다.
3. 단계 종료 시 성공/실패와 역할별 보고를 JSON 객체 1개로 반환한다. 작업을 끝낼 수 없는 새 판단이 있으면 실패 근거와 판단 후보를 함께 반환한다. 분석 자체가 끝났고 후속 설계에서 판단이 필요하다면 분석 성공과 후속 단계 대상 후보를 함께 보고할 수 있다.
4. 서버가 결과·근거를 검증하고 현재 상태와 원본 보고를 저장한다. 판단 후보와 blocking=true인 후보의 영향 보류는 같은 트랜잭션에서 기록하여 후속 배정과 경쟁하지 않게 한다. blocking=false 후보는 참고용이며 배정을 막지 않는다.
5. 서버가 필요한 trigger만 오케스트레이터 큐에 추가한다. 일반 성공은 기존 계획에 따라 다음 단계로 진행한다. 오케스트레이터 실패로 모듈 보고를 버리지 않는다.

v2도 **최종 결과 보고만** 다룬다. 중간 로그 스트림·퍼센트·heartbeat를 이 JSON에 섞지 않는다. 해당 기능을 추가하려면 별도의 관찰 이벤트 계약과 재연결·중복 처리 시험이 필요하다.

### 11.2 요청 확장과 식별자

일반 모듈 요청은 4절의 입력을 유지하고 다음 필드를 추가/변경한다. 리뷰도 같은 원칙을 적용하되 7절처럼 코드 결과 `implementation`을 함께 받는다.

| 필드 | v2 요청 규칙 |
|---|---|
| `schema_version`, `message_type` | `2`, `module_request` |
| `report_id` | 서버가 이 호출의 최종 보고에 미리 할당한 고유 ID. 재전송해도 유지 |
| `plan_version` | 배정한 계획 버전. agent가 올리거나 추정하지 않음 |
| `role` | analyst/designer/implementer/builder/reviewer/verifier/integration 중 배정 역할 |
| `input_result_refs` | 필요한 이전 보고의 `{report_id, sha256}` 배열. 분석 등 선행 결과가 없으면 빈 배열 |
| `report_expectations` | 필수 보고 항목·시험 사례·현재 source 기준·읽기/쓰기 허용 범위·역할 지침 버전 |

job/module/stage/attempt/session/fingerprint는 계속 서버가 발급한다. 리뷰의 attempt_id는 부모 코드 실행과 연결하되, **리뷰 session_id와 report_id는 별도**다. 통합은 module_id가 null이다. 별도 저장소의 자체 task/session ID는 확장 메타데이터로 남길 수 있지만 대시보드 ID를 대체하지 않는다.

### 11.3 공통 결과 — 각 agent가 반드시 갱신할 데이터

| 필드 | v2 보고 규칙 |
|---|---|
| `schema_version`, `message_type` | 필수 `2`, `module_result` |
| `job_id`, `module_id`, `stage`, `attempt_id`, `session_id`, `report_id`, `plan_version`, `fingerprint` | 모두 필수. 요청값 그대로. 성공·실패·리뷰 모두 일치 검사 |
| `input_result_refs` | 요청의 참조 배열 그대로. 과거 결과를 현재 기준인 것처럼 교체하지 않음 |
| `source_revision` | 필수. 실제 수행 대상 또는 코드 변경 후 식별 가능한 소스 기준. 실패 중 수정했어도 실제 현재 기준 보고. 확인 자체가 불가능한 실패는 null과 아래 unavailable_reasons로 표시하며 현재 성공 기준으로 사용 금지 |
| `outcome`, `evidence` | v1과 같이 SUCCEEDED/FAILED와 비어 있지 않은 사실 기반 설명 |
| `error_class`, `cause_key` | 실패 분류 필수, 코드 FIX면 안정적인 cause_key 필수. v1 오류 분류 정책 유지 |
| `artifact` | 모듈 빌드 성공 시 v1의 파일 경로/해시 계약 유지. agent가 runtime artifact ID를 만들지 않음 |
| `report` | 아래 공통 보고 객체 필수 |

`report`의 필수 항목:

| 필드 | 형식·내용 |
|---|---|
| `summary` | 문자열. 이번에 수행한 범위·완료한 내용·남은 문제 |
| `details` | 역할별 구조화 객체. 아래 11.4절 참조 |
| `evidence_refs` | `{path, sha256, kind}` 배열. 작업 폴더 내 보고서/로그/diff 등, kind는 report/log/diff/image. 추가 파일이 없으면 빈 배열 |
| `test_results` | `{case_id, status, source_revision, artifact_sha256, evidence_paths}` 배열. status는 PASS/FAIL/NOT_RUN, 이미지 미사용이면 artifact_sha256=null. 시험이 없으면 빈 배열 |
| `decision_requests` | 새 판단 후보 배열. 없으면 빈 배열. 11.5절 형식 |

시험 실행 여부와 근거는 wrapper가 확인하고 agent의 문장만으로 PASS를 채우지 않는다. `evidence_paths`는 등록 대상으로 보고한 evidence_refs.path를 참조한다. 파일 참조는 서버가 허용 경로·실제 파일·해시를 검증한 후 정규화한다. 서버 내부 보고 해시는 수신 JSON의 정규화된 내용으로 계산하며 오케스트레이터의 result_refs에 사용한다. 파일 해시와 보고 객체 해시를 혼동하지 않는다.

### 11.4 역할별 details와 완료 조건

| 역할 / stage | `report.details` 필수 항목 | 완료 판단에 필요한 의미 |
|---|---|---|
| analyst / analysis | `vendor_changes`: change_id, disposition, rationale, affected_files, dependency_module_ids, required_cases를 가진 배열 | 변경별 already_upstream/port_required/excluded/needs_decision 제안. excluded는 승인된 결정 근거 없으면 확정하지 않음. 변경 ID는 입력 기준과 연결 |
| designer / design | `design_summary`, `target_files`, `interface_impacts`, `dependency_module_ids`, `verification_plan` | 선택한 수정 방법·호환성·의존·검증 방법. 모호한 설계는 decision_requests로 분리 |
| implementer / code | `changed_files`, `diff_path`, `fix_description`, `previous_attempt_difference` | 실제 diff 파일은 evidence_refs로 연결. 원본 재생성으로 기존 수정 제거 금지. 실패도 남은 diff·소스 기준 보존 |
| builder / build | `build_profile`, `command_summary`, `exit_code`, `target_description` | 실제 빌드 결과와 로그. command_summary는 수행 사실이며 오케스트레이터가 그대로 실행할 명령이 아님 |
| reviewer / review | `reviewed_source_revision`, `reviewed_diff_sha256`, `findings` | 구현 결과의 정확한 revision/diff. findings는 severity/location/description/recommendation/evidence_paths 배열. 검토 통과 outcome=SUCCEEDED |
| verifier / verification | `verification_scope`, `required_case_ids`, `limitations` | test_results의 필수 사례 결과와 대상 일치. 미실행 필수 사례가 있으면 전체 검증 성공 금지 |
| integration / integration | `included_modules`, `build_profile`, `required_case_ids`, `limitations` | included_modules는 module_id/source_revision/report_id 배열. 전체 실제 통합 대상과 회귀 결과 대조 |
| 사람 / device_test | agent 보고 없음 | 필수 사례 PASS/FAIL만 사람이 입력. 선택 메타데이터를 v2 도입으로 필수화하지 않음 |

분석의 vendor_changes는 v2에서 개별 검증·반영할 대상이다. 현재 v1의 `port_required` 일괄 표시를 v2 처리에서 그대로 재사용하면 안 된다. 누락 변경은 미분류로 남기며 필수 추적성 확인 전 계획/최종 완료를 확정하지 않는다. 각 필드의 정확한 JSON Schema는 O1에서 이 표를 기준으로 고정한다.

실패로 생성/확인하지 못한 역할별 자료는 해당 필드를 null로 두고 `report.details.unavailable_reasons` 객체에 필드명과 이유를 적는다. 예를 들어 빌드 시작 전 환경 오류이면 exit_code=null과 원인을 보고한다. 없는 로그/diff를 만들었다고 쓰지 않는다. 이 예외는 FAILED 결과에만 적용하며 SUCCEEDED의 필수 자료/근거 누락은 거부한다. 알고 있는 대상·ID·입력 참조와 실패 근거는 계속 필수다.

### 11.5 사람이 결정해야 하는 항목

각 `decision_requests` 항목은 다음을 포함한다.

- `candidate_key`: 동일 판단 원인에 재시도 동안 유지하는 키. attempt ID/시간을 붙이지 않는다. 서버는 job/대상/키를 함께 사용해 중복을 판정한다.
- `question`, `options`(서로 구분되는 문자열 배열), `recommendation`: 결정할 내용과 선택지·근거 있는 권장안.
- `affected_module_ids`, `affected_stages`: 실제 영향을 받는 기존 대상 ID·단계 배열. 불명확하면 근거를 명시하고 현재 대상부터 보류한다.
- `blocking`: 지정 단계의 진행에 결정이 필요한지 여부.
- `evidence_paths`: 해당 질문의 근거 파일 참조. 파일 외 근거는 evidence/summary에 명시한다.

분석 완료 후 설계 판단이 필요한 v2 보고 예시다. ID·revision은 설명용이며 실제 요청과 수행 결과로 바꾼다.

```json
{
  "schema_version": 2,
  "message_type": "module_result",
  "job_id": "job-example",
  "module_id": "module-ethernet-example",
  "stage": "analysis",
  "attempt_id": "attempt-analysis-example",
  "session_id": "analyst-session-example",
  "report_id": "report-analysis-example",
  "plan_version": 1,
  "fingerprint": "copy-the-request-fingerprint",
  "input_result_refs": [],
  "source_revision": "0123456789abcdef0123456789abcdef01234567",
  "outcome": "SUCCEEDED",
  "evidence": "벤더 변경 분석을 완료했다. 저전력 모드의 기존 동작 유지 여부는 설계 전에 사람이 결정해야 한다. 코드 수정과 장비 시험은 수행하지 않았다.",
  "report": {
    "summary": "분석 대상 변경 1건의 신규 OS 차이를 확인했고 설계 판단 1건을 제안한다.",
    "details": {
      "vendor_changes": [
        {
          "change_id": "vendor-change-example",
          "disposition": "needs_decision",
          "rationale": "신규 OS의 저전력 동작이 기존 벤더 정책과 다르다.",
          "affected_files": ["drivers/net/example.c"],
          "dependency_module_ids": [],
          "required_cases": ["ethernet-suspend-resume"]
        }
      ]
    },
    "evidence_refs": [],
    "test_results": [],
    "decision_requests": [
      {
        "candidate_key": "ethernet.power.compatibility-policy",
        "question": "기존 벤더의 저전력 동작을 유지할지 신규 OS 기본 동작을 채택할지 결정이 필요하다.",
        "options": ["기존 동작 유지", "신규 OS 동작 채택"],
        "recommendation": "기존 제품 호환성 기준을 확인한 뒤 기존 동작 유지 여부를 결정한다.",
        "affected_module_ids": ["module-ethernet-example"],
        "affected_stages": ["design", "code", "build", "verification", "device_test"],
        "blocking": true,
        "evidence_paths": []
      }
    ]
  }
}
```

이 보고가 accepted여도 agent가 Jira를 전송하거나 결정의 답을 정하지 않는다. 서버의 후보 접수 → 오케스트레이터 제안 → 내부 Decision/Jira 어댑터 흐름을 따른다. 이미 진행 중인 작업은 영향 정책에 따라 결과 보류/안전 종료를 처리하고, 시작하지 않은 의존 작업은 배정하지 않는다. 독립 작업은 계속한다.

### 11.6 중복·실패·이전 버전 처리

- 서버는 `report_id`와 정규화 내용 해시로 재접수를 비교한다. 같은 보고는 한 번만 반영하고 다른 내용으로 같은 ID를 사용하면 충돌로 남긴다. 수정된 결과를 덮어쓰지 말고 새 attempt/보고로 기록한다.
- 입력 ID·계획·fingerprint·선행 결과 해시가 다르면 현재 완료로 반영하지 않는다. 오래된 결과 원본은 이력으로 보존한다. 새 판단 후보와 보류도 오래된 보고로 현재 작업에 생성하지 않는다.
- v2 지원은 설정/비파괴 capability 확인 뒤 job에 고정한다. 요청이 v1이면 v1만 반환하고, 요청이 v2인데 wrapper가 미지원이면 명시적 연결 실패로 처리한다. 신규 계약을 v1로 조용히 낮추지 않는다.
- v1 자료는 서버가 확인한 ID/상태/근거만 읽어 조정 입력에 제공하고 `legacy_report`로 표시한다. 없는 분류·시험·판단 데이터는 미제공으로 표시한다. v2 수준의 필수 데이터가 필요하면 영향 작업만 자료 보완 대기한다.
- wrapper가 유효한 구조화 실패를 보고할 수 있으면 exit 0을 사용한다. 비정상 종료/시간 초과는 서버가 별도 기록한다. 실제 프로세스 상태 불명은 성공·실패로 추측하지 않는다.
- 상세 진행도/heartbeat는 이번 v2에 포함되지 않는다. 추가 필드를 보내도 지원을 의미하지 않는다. 기존 87개/3개 시험 PASS는 v2나 오케스트레이터 시험 PASS가 아니다.

## 12. Claude 수동 조정 패키지와의 연결

[수동 사용 안내](../agents/CLAUDE_ORCHESTRATOR_GUIDE.md)의 agent는 준비된 snapshot과 근거 파일을 읽는다. 이 패키지를 추가해도 위 모듈 v1/v2 수신 기능은 달라지지 않는다. 외부 모듈 agent는 계속 지원되는 wrapper 계약으로 worker에 보고하고, v2 미지원 데이터는 보고서 참고자료로 구분한다. 수동 프로필의 report_id/hash는 입력 작성자가 확인한 자료에 연결하며 서버 AgentReport 저장이 구현됐다고 주장하지 않는다. 조정 응답을 module_result나 coordinate 응답으로 전송하지 않는다.

## 13. 환경 설정 편의 변경

소스 기준 입력이 빈칸이면 실제 새 작업 시작 시 `new_base`의 깨끗한 Git HEAD를 읽어 job/profile에 고정한다. worker가 전달하는 source_revision 필드와 결과 상관관계 계약은 그대로다. 설정/새 작업 사이에 소스가 바뀔 수 있으므로 환경 점검의 값을 영구 기준으로 사용하지 않는다. 자동 기록은 전체 입력 파일의 snapshot이나 실제 수정 결과의 revision 검증을 대신하지 않는다.

기본 도구 연결은 D-42에 따라 내장 CLI로 변경했다. 기존 브리지의 기본 경로는 고급 호환 모드에서만 제공한다. [설정·연결 안내](../agents/ENVIRONMENT_AND_BRIDGES.md)를 함께 전달한다.


## 12. 내장 CLI와 v1 정규화 — D-42 현재 구현

설정 `runner: native`이면 내장 어댑터가 v1 요청을 한 단계 작업 프롬프트와 결과 schema로 변환한다. 실행 토큰·owner·프로필은 모델 입력에서 제외한다. 역할 지침은 새 job에 고정한 내용을 전달한다.

- Claude는 structured_output, OpenCode/Codex는 JSON 이벤트의 최종 결과와 완료 이벤트를 읽는다. 자연어 완료 문장·중간 퍼센트는 해석하지 않는다.
- native 역할 결과는 `outcome`, `evidence`, `source_revision`, `error_class`, `cause_key` 문자열을 모두 반환한다. 성공이면 오류 두 필드는 빈 문자열이다. 요청에 attempt_id/fingerprint가 있으면 성공/실패 모두 정확히 반환한다. schema 외 임의 상태 필드는 거부한다.
- external_session_id는 모델이 만들지 않고 CLI envelope/event에서 수집한다. Claude의 명시 세션 ID와도 대조한다. 코드·리뷰는 다른 논리 세션이며 review에 외부 세션 ID도 기록한다.
- 코드 성공 시 서버가 작업 파일 내용 SHA-256을 source_revision으로 고정한다. 모델 보고 값은 reported_source_revision으로 남긴다. review 직후 같은 내용인지 검사한다. 원본 커밋 자동 기록과 수정 결과 내용 식별자는 다른 값이다.
- 빌드/검증/통합은 모델 보고 대신 등록 명령을 실행하고 서버가 v1 결과를 만든다. 빌드는 실제 갱신된 파일을 해시·등록한다. 검증/통합 스크립트의 nonzero는 실패이며 사례별 상세 시험 보고 v2는 아직 미구현이다.
- timeout·출력 제한·도구 비정상 종료·로그인 문제를 실패로 기록한다. 프로세스 그룹 종료가 확인되지 않으면 서버 내부 UNKNOWN과 잠금을 유지한다. 모델이 UNKNOWN으로 완료를 보고하는 계약은 아니다. 계약 오류는 CONTRACT이며 자동 코드 FIX 횟수를 늘리지 않는다. 내장 CLI stdout+stderr 한도는 4MiB다. 기존 브리지의 1MiB 결과 한도와 구분한다.
- 분석·설계·조정·질문은 읽기 역할이다. 구현 중 Bash/하위 agent를 자동 허용하지 않으므로 컴파일 확인은 다음 빌드/검증 단계에서 한다. 추가 판단이 필요한 경우 FAILED 근거로 보고하며 자동 Decision/Jira 후보 접수는 v2 후속이다.

내장 연결 추가는 모듈 v2나 자동 orchestrate 구현이 아니다. 중간 상태 push·세션 프로세스 재접속·OS 수준 원본 snapshot 격리도 여전히 후속 범위다. 실제 CLI 인수 전에는 역할 지침과 CLI 권한/확장 동작을 지정 Linux에서 확인해야 한다.
