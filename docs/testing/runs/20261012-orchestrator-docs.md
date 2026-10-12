# 2026-10-12 오케스트레이터 문서 검증

- run_id: 20261012-orchestrator-documentation
- executor: Codex
- scope: documentation only
- 정책: D-39, ADR-06 / 신규 요구사항 RQ-30~34 / 신규 제품 시험 T-71~85
- 제품 코드·시험·DB·runtime·환경 설정 변경: 없음
- 제품 시험 재실행: 없음. 아래 PASS는 문서 검사다.

| 검증 | 결과 | 근거 |
|---|---|---|
| 문서 링크·요구사항/시험/CSV 연결 | 검사 출력 참조 | [doc-validation.json](20261012-orchestrator-docs-evidence/doc-validation.json) |
| JSON 예시·필수 구조·기존 결과 보존·코드 동일성 | 검사 출력 참조 | [contract-document-check.json](20261012-orchestrator-docs-evidence/contract-document-check.json) |
| 신규 제품 T-71~85 | NOT_RUN | 구현·실제 제품 시험 전 |
| 실제 Linux/CLI wrapper/Jira/장비 | NOT_RUN | 문서 작업 범위 |
| 독립 Claude 검토 | NOT_REVIEWED | 수행하지 않음 |

## 반영한 문서

[파일별 문서 해시/변경 목록](20261012-orchestrator-docs-evidence/document-manifest.json)에 기록한다. 오케스트레이터 책임/권한/호출/제안/복구, 모듈 보고 v2, 요구사항·구조·상태·저장/API·UI·역할·운영, 구현 계획·테스트 목록/최신 결과, 문서 진입점·진행/결정/검토 기록을 함께 갱신했다.

현재 모듈 v1 계약을 보존하고 새 v2 및 조정 판단 계약은 미구현으로 표시했다. 실행 배정은 기존 worker만 담당한다. 모듈 보고는 DB에 먼저 저장하고 조정 호출이 결과 수집을 막지 않도록 정의했다. 신규 인수 15개를 NOT_RUN으로 추가했으며 기존 70개 결과와 과거 실행/실패 기록은 변경하지 않았다.

## 내용 정합성 검토

Codex가 문서 간 책임/필드/상태를 대조했고 다음을 명시했다. 독립 Claude 검토를 수행했다는 의미는 아니다.

- 조정 성공·제안 접수·실제 작업 성공을 분리한다. 필수 코드 리뷰/수동시험/최종 사람 검토를 유지한다.
- 결과와 판단 후보 및 blocking 범위 보류를 원자적으로 저장한다. nonblocking 후보는 배정을 막지 않는다.
- 조정 감사 기록만으로 자신의 기준 버전이 무효화되지 않게 하고 실제 계획/실행 변경 때만 버전을 올린다.
- 기존 후보가 일반 실패로 분류되어도 자동 보류 해제 명령을 만들지 않으며 근거 있는 운영 확인 경로를 사용한다.
- 실패로 만들지 못한 자료는 null과 이유로 보고할 수 있고 성공에 같은 예외를 적용하지 않는다.
- 현재 구현의 정해진 모듈 목록/종료 JSON, 목표 계획 제안/역할별 v2 보고/후보 자동 접수를 구분한다.
- 모듈·조정 계약 버전, 소스/근거 해시, 실행 ID, 세션 ID를 혼동하지 않으며 외부 wrapper와 버전을 협의한다.

[이전 제품 검증](20261012-local-entry-agent-contract.md)의 source manifest와 현재 코드를 비교했다. 코드가 같다는 확인은 새 기능이 동작한다는 시험이 아니다. 제품 baseline은 갱신하지 않는다.

## 최종 검사 결과

문서 검사 PASS: 상대 링크 156개, 요구사항 34개, 시험 목록/CSV 85개, 전체 NOT_RUN 75개. JSON 예시 8개 PASS. 제품/시험 파일 32개 내용 동일, 기존 결과 70개 보존, 신규 15개 NOT_RUN.
