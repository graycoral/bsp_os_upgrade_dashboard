# 데이터 모델·보존·유효성

아래는 목표 논리 스키마다. 현재 저장 구조와 확장에 필요한 migration은 이 문서 하단에 구분한다. 모든 시간은 UTC 저장, UI는 사용자 시간대로 표시한다. ID는 추측 가능한 파일 경로로 사용하지 않으며 외부 ID와 내부 ID를 분리한다.

이 표는 목표 영속 모델이며 외부 에이전트에 보내는 JSON 필드 목록이 아니다. 실제 전송 필드·현재 미지원 사항은 [에이전트 상태·결과 보고 계약](AGENT_STATUS_CONTRACT.md)을 따른다.

| 엔터티 | 주요 필드 | 제약·관계 |
|---|---|---|
| ExecutionProfile | id, host, account, workspace_root, source_roots, output_root, build_profile, credential_ref, revision | 비밀 값 대신 참조. 변경은 새 revision |
| Job | id, profile_revision, mode, source_snapshot_id, plan_version, state, health, state_version, created_by | mode는 UI 진입 정보. 실제 실행 위치 Linux |
| SourceSnapshot | id, old_base, vendor_tree, new_base, working_revision, config_hash, toolchain_hash | 커밋/콘텐츠 해시로 고정. mutable branch 이름만 저장 금지 |
| PlanVersion | job_id, version, module_manifest, dependency_edges, required_units, confirmed_by, confirmed_at | 확인된 버전 불변. 변경은 신규 버전 |
| Module | id, job_id, stable_key, display_name, group, active, introduced_version | job+stable_key 유일. 삭제 대신 비활성 이력 |
| VendorChange | id, source_refs, intent, disposition, rationale, module_ids, decision_id | disposition: already_upstream / port_required / excluded / needs_decision |
| WorkItem | id, job_id, module_id nullable, stage, unit_key, required, weight, input_fingerprint, status, reason_code | stage는 analysis/design/code/build/verification/device_test 등. 현재 필수 단위 |
| Dependency | work_item_id, required_result_key, required_fingerprint | DAG 검사. 단계 이름만으로 통과 처리 금지 |
| Attempt | id, work_item_id, ordinal, command_id, role, tool, model, session_id, process_ref, token, status, started_at, ended_at, error_class, cause_key | 작업별 ordinal 유일. active attempt 최대 하나 |
| Session | id, job_id, role, tool, external_id, scope, status, last_seen_at, recovery_mode | 조정 세션과 역할 실행 세션 별도 |
| Result | id, attempt_id, input_fingerprint, outcome, validity, evidence_refs, invalidation_reason | 과거 결과 불변, 유효성 변경은 감사 이벤트 추가 |
| Review | id, authored_revision, author_tools, reviewer_tool, reviewer_session, findings, outcome, evidence_ref | 작성 대상이 바뀌면 CURRENT 승인 아님 |
| Artifact | id, job_id, attempt_id, relative_path, sha256, bytes, source_revision, config_hash, bundle_id | 경로 이탈 금지, 불변 파일, 다운로드 권한 확인 |
| ManualTest | id, attempt_id, board_id, bundle_id, image_hashes, test_plan_revision, operator, performed_at, cases, evidence_refs | 사례별 PASS/FAIL 필수, 보드/수행자/수행 시각/근거 선택. 현재 이미지·소스·계획 자동 연결; 입력한 선택값은 검증 |
| Decision | id, job_id, question, options, affected_work_ids, status, selected_option, decided_by, evidence_ref, applied_revision | resolved와 applied 구분 |
| JiraLink | decision_id, connection_revision, issue_key, remote_version, sync_status, last_sync_at | decision별 생성 intent 유일 |
| Command | id, idempotency_key, job_id, actor, action, payload_hash, expected_version, status, result_ref | 동일 actor/scope/key는 같은 payload만 허용 |
| ResourceLease | resource_key, owner_attempt, token, expires_at, process_confirmation | lease 만료만으로 재배정 금지 |
| Event | id, job_id, sequence, type, actor, attempt_id, payload, occurred_at | job별 sequence 유일·단조 증가. 감사 이력 append-only |
| Outbox | id, intent_key, adapter, payload_ref, status, retry_at, external_ref | DB 변경과 intent 동일 트랜잭션. 원격 성공 불명 상태 구분 |

## 입력 fingerprint와 무효화

정규화된 source revision + 관련 dependency result/artifact 해시 + 설정 revision + 시험 계획 revision + 역할 지침 revision을 해시한다. timestamp처럼 결과에 영향 없는 값은 제외한다. 도구 버전·빌드 환경은 provenance에 남기며 결과에 영향을 주면 fingerprint에 포함한다.

입력 변경 시 의존 그래프를 따라 영향받는 결과를 INVALIDATED로 표시한다. 정확한 영향 범위를 증명할 수 없으면 보수적으로 관련 후속 검증을 무효화하고 범위를 기록한다. 과거 결과 삭제나 현재 결과로의 복사는 금지한다. 리뷰, 빌드 이미지, 수동 시험도 동일 규칙을 따른다.

## 트랜잭션 경계

1. 명령 중복 검사 → 기대 버전 검사 → command/상태/event/outbox 저장을 원자 처리.
2. 작업 claim → 게이트 재검사 → 자원 lease/token → attempt intent 저장을 원자 처리.
3. 결과 접수 → attempt/token/fingerprint 검증 → 결과/event/집계 버전 갱신을 원자 처리.
4. 원격 CLI/Jira 호출은 DB 트랜잭션 밖에서 수행한다. 원격 결과 반영에는 중복 및 늦은 응답 검사를 적용한다.

## 보존·이전·복구

- schema_version과 순차 migration을 관리한다. 운영 DB 변경 전 일관된 백업을 만들고 복원 시험을 수행한다. SQLite 실행 중 파일 단순 복사 대신 지원되는 일관된 백업 방식을 사용한다.
- DB 백업과 artifact manifest를 함께 보존한다. 복구 시 파일 존재·해시·누락을 검사하고 누락된 근거를 PASS로 인정하지 않는다.
- 시험·결정·실패 이력은 수동 삭제하지 않는다. 보존 기간은 운영 정책에서 정하고 삭제 시 감사 이력·참조 무결성 유지. 자격증명과 민감 원문은 최소 수집한다.
- 코드 롤백 시 DB 스키마 호환성을 먼저 확인한다. 데이터 손실을 수반하는 역 migration을 자동으로 실행하지 않는다.
- 1차 구현은 schema_version=1이며 jobs JSON, commands, events, leases, config, meta 테이블을 사용한다. 위 표는 목표 논리 모델로서 각 행이 별도 테이블로 구현된 것은 아니다. 이번 선택 입력 변경은 기존 JSON과 호환되어 테이블 이전이 필요 없다. 데모 수동 완료는 새 attempt에 simulation/manual_override를 기록한다.

## 오케스트레이터 확장 엔터티 — 신규, 미구현

전송 필드는 [조정 계약](ORCHESTRATOR_SPEC.md)과 [모듈 보고 계약](AGENT_STATUS_CONTRACT.md)에 두고, 아래는 저장·인덱스·참조 책임만 정의한다.

| 논리 엔터티 / 후보 테이블 | 보존 대상 | 필수 제약 |
|---|---|---|
| OrchestrationTrigger / orchestration_triggers | 원인 event·job·plan, 큐 상태, 소비한 조정 호출 | 동일 event/trigger 종류 중복 금지. 호출 결과 저장 전 소비 완료 금지 |
| OrchestrationRun / orchestration_runs | 호출 기준 snapshot·근거 해시·세션·상태·프로세스·응답·시간·예산 | job별 active 호출 최대 1. 재시작/질문과 동일 세션 경합 확인 |
| OrchestrationProposal / orchestration_proposals | 원본 제안·근거·검증 결과·적용/거부 사유·명령 ID | job/run/proposal_key 유일. 내용 해시 충돌 거부. 접수와 실행 결과 분리 |
| AgentReport / agent_reports | 원본 v1/v2 결과·정규화 사실·입력 참조·근거 파일·내용 해시 | report_id 유일. 같은 ID 다른 내용 거부. 과거/무효 결과 보존 |
| DecisionCandidate / decision_candidates | 출처 보고·동일 원인 키·질문/선택지/영향·내부 Decision 연결 | job/대상/후보 키로 중복 판정. 원본 질문이 달라지면 수정 이력 |
| ScopeHold / scope_holds | 후보/결정·영향 모듈/단계·보류 이유·해제 근거 | 원인 참조 필수. 조정 세션 종료로 자동 해제 금지 |

트리거 상태는 PENDING/ASSIGNED/CONSUMED, 호출 상태는 PENDING/RUNNING/SUCCEEDED/FAILED/UNKNOWN/CANCELLED, 제안 상태는 RECORDED/APPLIED/WAITING_USER/BLOCKED/REJECTED/STALE을 기준으로 한다. 호출 완료와 그 제안 적용은 별개다. 후보 분류/해제 이력과 Decision의 OPEN/RESOLVED/APPLIED도 별도로 보존한다.

새 트랜잭션 경계:

1. v2 결과의 ID/해시/현재 기준 검증 → AgentReport·attempt 결과·DecisionCandidate·blocking 후보의 ScopeHold·trigger 기록을 함께 commit. 참고용 후보는 ScopeHold를 만들지 않는다. 오래된 보고는 현재 보류/집계를 만들지 않는다.
2. 트리거 배정 → job별 유일 조정 호출 생성. LLM 호출은 트랜잭션 밖에서 수행한다.
3. 호출 응답·각 제안 원문 저장 → 현재 상태/게이트 검사 → 기존 command 접수와 제안 적용 결과 연결. 프로세스 실행과 Jira 전송은 commit 후 실행한다.
4. 검증된 Decision 제안 → 기존 후보/Decision 검색 → 새 내부 결정과 전송 의도 저장. 원격 재시도에 같은 내부 ID를 사용한다.

순수 조정 감사/큐 기록과 job 실행 상태 버전을 분리한다. 전자의 저장 자체가 조정 입력 기준을 무효화하지 않으며 실제 계획/명령/모듈 상태 변경 때만 실행 버전을 갱신한다.

테이블 이름과 인덱스의 최종 SQL은 O1/O2에서 고정한다. 실제 확장에는 migration 및 기존 jobs JSON/이력/명령과의 호환 시험이 필요하다. **이번 문서 변경에서는 DB를 수정하지 않는다.** DB schema 버전은 모듈 전송 v2나 조정 전송 v1과 별개다. 백업에는 새 큐·제안·보고·보류와 근거 파일 manifest를 포함하고 복원 후 중복 실행 여부를 검증한다.

## 수동 Claude 패키지의 현재 범위

수동 Claude 패키지는 파일 기반 입력/결과와 패키지 manifest만 사용한다. DB migration, AgentReport/OrchestrationRun/Proposal 저장, 영속 중복 방지를 구현한 변경이 아니다. 출력 해시는 파일 비교용이며 명령 접수 기록이 아니다. [사용 안내](../agents/CLAUDE_ORCHESTRATOR_GUIDE.md)를 따른다.

소스 기준 자동 기록 변경은 DB schema_version=1을 유지한다. 설정의 source_revision 빈 문자열은 자동 선택 의도이며, 새 job.source_revision과 고정 profile.source_revision에는 실제로 읽은 커밋을 저장한다. 기존 작업/기존 명령 결과를 수정하지 않는다. 별도 provenance/snapshot 테이블을 구현한 변경은 아니다.


## D-42 현재 JSON 확장

DB schema_version=1과 기존 테이블을 유지한다. 저장 설정 Profile에는 native/bridge 선택·경로/지침/명령 필드를 추가한다. native 새 job.profile에는 절대 agents 경로, tool_checks, instruction_snapshots를 함께 고정한다. 과거 job.profile은 재검증/변환하지 않고 runner가 없으면 기존 bridge 경로로 실행한다.

native 코드 결과는 실제 작업 내용 source_revision, 모델 보고 reported_source_revision, revision_kind를 보존한다. 모듈 결과/리뷰/질문에 CLI 외부 세션 ID를 기록한다. session.history는 연결 재시도 전 실패 기록을 보존한다. 이 확장은 O2의 AgentReport/Proposal/DecisionCandidate 테이블 구현이 아니다.
