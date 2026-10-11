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

최신 로컬 제품 시험은 [20261012 구현 검증](20261012-implementation.md)을 참고한다. 모의 시험과 실제 Linux/장비/Jira 검증을 구분한다. 문서 검사 PASS를 제품 PASS로 간주하지 않는다.
