# 실행별 시험 이력

파일명: `YYYYMMDD-HHMMSS-<scope>-<run_id>.md`. 같은 실행 파일을 후속 시험으로 덮어쓰지 않는다. 잘못 기록한 결과는 정정 기록을 추가하고 원래 기록을 연결한다. 민감 로그는 비밀 제거 후 증거 저장소 링크/해시로 참조한다.

```text
run_id:
started_at / ended_at:
executor / tool:
scope: unit | contract | integration | ui/e2e | live | hardware-manual | documentation
code_revision:
test_revision:
dirty_diff_hash: (미커밋 코드 시험 시 필수)
environment / dependency_versions:
command_or_manual_steps:
test_id | status | actual_result | evidence_ref | defect_id
summary:
blocked_and_not_run:
supersedes_run_id: (재시험인 경우)
```

최신 로컬 제품 시험은 [20261012 키 없는 진입·에이전트 계약 검증](20261012-local-entry-agent-contract.md)을 참고한다. 이전 [20261012 구현 검증](20261012-implementation.md)과 실패 기록은 보존한다. 모의 시험과 실제 Linux/장비/Jira 검증을 구분한다. 문서 검사 PASS를 제품 PASS로 간주하지 않는다.

최신 **문서 전용 검사**는 [20261012 오케스트레이터 설계 검증](20261012-orchestrator-docs.md)이다. 신규 오케스트레이터·모듈 보고 v2 구현은 미착수이며, 기존 제품 시험과 별도 실행으로 관리한다.

최신 패키지 및 기존 기능 회귀 시험은 [20261012 Claude agent 패키지](20261012-claude-agent-package.md)다. 수동 Claude 역할 파일/검증 도구를 새로 시험했으며 실제 Claude 호출은 미실행이다. 자동 조정 O1~O5/모듈 보고 v2의 인수 결과와 구분한다.

최신 설정 변경 및 회귀 실행은 [20261012 소스 자동 기준·브리지 기본값](20261012-settings-defaults.md)이다. 이전 Claude 패키지 시험과 실패 이력은 보존한다.
