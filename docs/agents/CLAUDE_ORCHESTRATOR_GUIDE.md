# Claude 오케스트레이터 사용 안내

상태: **수동 호출 패키지 구현 / 자동 대시보드 연동 미구현**. Python 3.11 이상 표준 라이브러리만으로 패키지 검사·배포·입출력 검증을 수행한다. 실제 Claude 호출, BSP 수정/빌드/장비시험, Jira 전송은 검증 도구가 실행하지 않는다.

## 1. 파일과 역할

| 파일 | 용도 |
|---|---|
| `.claude/agents/bsp-upgrade-orchestrator.md` | Claude Code에서 사용할 실제 agent 정의. Read/Glob/Grep만 허용, 현재 세션 모델을 상속 |
| `scripts/claude_orchestrator.py` | 독립 실행 가능한 입력·응답 검사 및 새 디렉터리로 패키지 내보내기 |
| `examples/claude-orchestrator/` | 가상 작업의 입력·응답·실패 근거 예시. 실제 BSP 결과가 아님 |
| `docs/design/ORCHESTRATOR_SPEC.md` | 역할·제안 종류·자동 연동 목표의 단일 기준 |
| `docs/design/AGENT_STATUS_CONTRACT.md` | 모듈별 보고 필드의 단일 기준. 현재 v1과 미래 v2 구분 |
| `docs/roles/RUNTIME_ROLES.md` | 외부 모듈 agent별 업무 지침 |

프로젝트의 `.claude/agents/` Markdown과 YAML frontmatter 구성은 [Claude Code 공식 subagent 문서](https://code.claude.com/docs/en/sub-agents)를 따른다. 현재 환경에 Claude CLI가 없어 실제 검색·호출은 아직 확인하지 않았다. 파일 검사 PASS와 모델 동작 성공을 구분한다.

## 2. 바로 확인하기

대시보드 저장소 루트에서 실행한다. Linux에서는 `python3`, Windows에서는 설치 환경에 따라 `py -3`를 사용한다. 별도 라이브러리 설치는 필요 없다.

```bash
python3 scripts/claude_orchestrator.py check-agent
python3 scripts/claude_orchestrator.py check-request --request examples/claude-orchestrator/request.json --workspace examples/claude-orchestrator
python3 scripts/claude_orchestrator.py validate --request examples/claude-orchestrator/request.json --result examples/claude-orchestrator/result.example.json --workspace examples/claude-orchestrator
```

예시의 기대 결과는 `VALID_REVIEW_ONLY`, `freshness: NOT_CHECKED`, RETRY의 `WAITING_USER`다. 유효성 검사일 뿐 재시도나 작업 완료를 수행하지 않는다. `--current-request`로 같은 작업의 **새로 확인한 입력**을 함께 주면 버전·계획·fingerprint 변화 시 `STALE`로 표시한다. 자기 입력을 다시 넘기는 것은 최신 상태 확인 증거가 아니다. 버전이 같더라도 실제 상태를 거짓으로 작성했는지는 이 도구가 알 수 없다.

다른 서버로 옮길 때는 새로운 폴더로 내보낸다.

```bash
python3 scripts/claude_orchestrator.py export --output /path/to/new-bsp-orchestrator
```

기존 경로는 덮어쓰지 않는다. 출력에는 agent, 도구, 이 안내, 예시, 세 개의 기준 문서 사본과 `package-manifest.json`이 들어간다. 원래 프로젝트의 `.claude`나 `CLAUDE.md`, 대시보드 DB, 인증정보를 복사/수정하지 않는다. 기준 문서 사본의 저장소 내부 링크는 텍스트로 바뀐다. 최신 원문이 바뀌면 **새 경로로 다시 내보낸다**. 내보낸 폴더에서 위 검사 명령을 동일하게 실행할 수 있다.

## 3. 사용자가 Claude에서 실행할 순서

1. 저장소 루트 또는 내보낸 폴더에서 Claude Code를 연다. 이미 실행 중인 세션에서 `.claude/agents`가 처음 생겼다면 세션을 재시작한다.
2. 아래처럼 명시적으로 agent 이름과 입력·근거 경로를 지정한다. 최초에는 제공된 가상 예시를 사용한다.

```text
bsp-upgrade-orchestrator 에이전트를 사용해 주세요.
docs/agents/CLAUDE_ORCHESTRATOR_GUIDE.md를 읽고,
examples/claude-orchestrator/request.json을 처리해 주세요.
근거 workspace는 examples/claude-orchestrator 입니다.
실제 실행 없이 검토할 orchestration_result JSON만 반환해 주세요.
```

3. 반환된 JSON만 `result.actual.json` 같은 새 파일에 저장한다. 예시 응답을 실제 응답으로 덮어쓰거나 Claude가 실행한 증거라고 기록하지 않는다. agent는 파일 쓰기 권한이 없으므로 저장은 사용자가 한다.
4. 위 `validate`의 `--result`를 실제 응답 경로로 바꿔 검사한다. 오류면 원래 입력·응답을 보존하고 원인을 확인한 후 새 응답 파일로 재시도한다.
5. 적절한 제안인지 사람이 검토한다. 현재 대시보드에서 필요한 계획 확인·실패 재시도·판단 등록은 기존 화면을 사용한다. 이 JSON을 현재 coordinate/module wrapper 설정에 넣지 않는다.

실제 BSP 시험으로 바꿀 때는 해당 실행 관리자가 확인한 상태와 결과로 입력을 준비한다. 다른 프로젝트의 agent 목록을 읽고 자동 등록하거나 실행하는 기능은 없다. 모듈들은 자신에게 배정된 단계 결과를 worker에 보고하며 오케스트레이터는 수집된 기록을 읽는다. 모듈별 작성 필드는 `AGENT_STATUS_CONTRACT.md` 11절, 현재 연결은 1~10절 v1을 따른다. v2 수신은 아직 구현하지 않았다.

## 4. 수동 입력 프로필: claude-manual-v1

최상위 입력·응답 필드는 `ORCHESTRATOR_SPEC.md` 5~6절 그대로다. 아래는 아직 고정되지 않았던 snapshot/constraints를 **오프라인 검토용으로만** 구체화한 프로필이며, 향후 서버 O1 스키마나 원본 DB 덤프를 의미하지 않는다. 비밀 값과 실행 token을 포함한 DB/profile 객체를 그대로 복사하지 않는다.

| 경로 | 필수 형식 / 작성 기준 |
|---|---|
| `snapshot.source_revision` | 실제 대상 revision 문자열 |
| `snapshot.plan_confirmed` | 현재 계획을 사람이 확인했는지 boolean |
| `snapshot.prerequisite_complete` | 선행 그룹 전체가 현재 기준으로 유효하게 완료됐는지 boolean. 단순 퍼센트에서 추측 금지 |
| `snapshot.paused`, `snapshot.writer_unknown` | 실제 중지 상태 / 공유 소스를 쓰는 실행의 종료가 불명인지 boolean |
| `snapshot.modules[]` | module_id, group(boot/main), blocked_stages, attempts. 기존 ID 유지 |
| `modules[].blocked_stages` | 현재 사람 판단에 의해 보류된 단계 목록 |
| `modules[].attempts[]` | 오래된 순서대로 attempt_id, stage, status, tool, error_class(null 가능), cause_key(null 가능), process_terminated(boolean) |
| `snapshot.decision_candidate_ids` | 확인된 후보 ID 목록. v1에 없으면 빈 배열. 없는 후보 ID를 생성하지 않음 |
| `constraints.profile` | `claude-manual-v1` |
| `constraints.allowed_proposals` | 다섯 제안 종류 중 이번 호출에서 허용할 부분집합 |
| `constraints.auto_retry_limit` | 반드시 0. 이 도구에 자동 적용 기능 없음 |
| `constraints.readable_evidence[]` | report_id, sha256(파일 바이트 기준 소문자 64자리), path(workspace 기준 상대 경로) |

status는 PENDING/RUNNING/UNKNOWN/FAILED/CANCELLED/SUCCEEDED, stage는 analysis/design/code/build/verification/device_test, tool은 opencode/claude/codex/build/human이다. result_refs마다 실제 읽을 파일이 필요하고 경로 이탈·외부 심볼릭 링크·해시 불일치는 거부한다. report_id는 입력 작성자가 확인한 저장 기록의 ID다. 현재 서버에 없는 조정 run/trigger는 수동 검토용 식별자로 명시하며 서버가 발급했다고 주장하지 않는다. 제공 예시는 모든 ID가 가상이다.

추가로 이 프로필에서 고정한 proposal.data는 다음과 같다. 실행 API 명령이 아니다.

- PLAN_CHANGE의 before/after는 name, group, scope, dependency_module_ids(기존 모듈 ID), required_cases를 가진 객체다. add의 before/module_id는 null, deactivate의 after는 null이다. 새 모듈 사이 의존 관계나 복합 DAG 자동 판정은 지원하지 않는다. 변경된 전체 계획의 타당성은 별도 검토한다.
- TOOL_ESCALATION의 추가 필드는 difficulty_evidence(문자열)다. 마지막 대상은 OpenCode의 code FIX 시도여야 한다. 실제 반복 횟수/난항의 정당성은 사람이 근거와 대조하며 자동 전환하지 않는다.
- DECISION은 candidate_ids(새 판단이면 빈 배열 가능), question, options(서로 다른 2개 이상), recommendation, affected_stages, blocking을 사용한다.
- VERIFICATION_PLAN은 source_revision, image_refs(입력 보고 참조), cases 배열을 사용한다. 사례는 case_id, method, expected_result를 갖는다. 계획이며 PASS/FAIL 필드는 받지 않는다.
- RETRY는 previous_attempt_id, cause_key, changed_approach다. 대상 모듈/단계의 가장 최근 시도를 참조해야 한다. device_test는 agent 재시도 대상이 아니다.

JSON은 1 MiB 이하 객체 한 개, 중복 키/미정의 필드/NaN을 허용하지 않는다. 실패 응답은 error_class를 포함하고 proposals는 빈 배열이다. 성공 응답의 제안도 모두 검토 대기다. UNKNOWN/종료 미확인, 중지, 계획 미확인, 일반 모듈의 선행 미완료, 관련 판단 보류는 재시도/전환 미리보기에서 BLOCKED로 나타낸다. 분석은 계획·부트로더 완료를 기다리지 않지만 해당 분석 자체의 중지/판단 보류는 존중한다.

## 5. 검증의 한계와 후속 구현

검증 종료 코드 0은 **입출력 형식 검사 통과**다. outcome FAILED, BLOCKED/STALE 제안도 구조가 올바르면 0이며 JSON의 내용을 함께 확인한다. 형식/파일/해시 오류는 종료 코드 2와 INVALID를 반환한다. freshness를 확인하지 않았으면 NOT_CHECKED다. 제안 해시는 동일 내용의 재전송 비교에 사용할 수 있지만 영속 중복 방지 저장소는 없다.

파일 해시 검사는 주어진 입력과 파일의 일치를 확인한다. 자료의 진실성·모델의 판단 품질·실제 권한 격리·공유 자원 잠금·재시작 복구·Jira 중복 방지·자동 proposal 적용은 증명하지 않는다. Claude 도구 allowlist도 OS sandbox나 경로별 권한 강제가 아니다. 실제 사용 시 필요한 자료만 넣은 workspace를 사용한다.

대시보드 자동 연동(O1~O5), 모듈 보고 v2, 실제 Linux CLI/BSP/장비/Jira 시험은 별도다. 최초 Claude 실행은 사용자가 수행하고 실제 입력·응답·검증 출력·모델/CLI 버전과 시각을 새 실행 기록으로 남긴다. 이번 패키지 시험만으로 T-71~85 또는 Claude 독립 검토를 PASS/APPROVED로 바꾸지 않는다.
