# 데이터 모델·보존·유효성

아래는 논리 스키마다. 실제 migration 파일과 DB 제약은 P1에서 구현한다. 모든 시간은 UTC 저장, UI는 사용자 시간대로 표시한다. ID는 추측 가능한 파일 경로로 사용하지 않으며 외부 ID와 내부 ID를 분리한다.

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
| ManualTest | id, attempt_id, board_id, bundle_id, image_hashes, test_plan_revision, operator, performed_at, cases, evidence_refs | 제출 revision 보존. 필수 사례·해시·보드·근거 검증 |
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
- 최초 구현에는 DB가 아직 없다. 이 문서는 기존 테이블이 존재한다는 뜻이 아니다.
