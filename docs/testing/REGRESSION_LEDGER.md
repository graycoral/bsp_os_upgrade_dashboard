# 회귀·결함 기록

확인된 로컬 결함과 수정은 아래 이력으로 관리한다. 실제 연동 미검증 위험을 발생한 버그로 작성하지 않는다.

| 필드 | 필수 내용 |
|---|---|
| regression_id | REG-0001부터 증가, 재사용 금지 |
| 증상·재현 | 입력·상태·동작·실제/기대 결과 |
| 영향 | RQ ID, 모듈/경로, 사용자 영향 |
| 최초 실패 | run_id, 코드/시험 revision, 증거 |
| 원인 | 확인 근거 또는 아직 미확인임을 명시 |
| 수정 | 수정 revision, 변경 요지, 대안/주의 |
| 방지 시험 | 기존/신규 T ID, 자동화 경로 |
| 재시험 | 새 run_id, PASS/FAIL, 증거 |
| 상태 | OPEN / FIXED_PENDING_VERIFICATION / VERIFIED / REOPENED |
| 정상 기준 | 검증 후 갱신한 baseline ID 또는 미반영 사유 |

같은 증상이 다시 발생하면 기존 REG를 REOPENED로 만들고 새 실패 실행을 연결한다. 이전 수정 기록을 지우지 않는다. 근본 원인이 다르면 새 REG를 생성하고 관련성을 연결한다.

## 2026-10-12 검증된 수정 기록

공통 수정 기준은 [구현 검증 기록](runs/20261012-implementation.md)의 code_revision/파일 manifest다. 새 코드가 커밋되기 전의 내용 해시로 시험 대상과 결과를 연결한다. 운영 baseline은 미등록이다.

| ID | 재현 / 원인 | 수정 / 방지 시험 | 최초 실패 → 재시험 | 상태 |
|---|---|---|---|---|
| REG-0001 | 첫 UI 빌드에서 nullable 객체 타입 검사 실패 | 명시적 null 보호 / TypeScript 빌드 | initial-build-failed → build PASS | VERIFIED |
| REG-0002 | 수동시험 select label 탐색이 선택지 텍스트와 충돌 | aria-label 명시 / T-59 UI | initial-browser-01-failed → 현재 browser PASS | VERIFIED |
| REG-0003 | 다른 모듈 상태 갱신 중 재시도 요청의 job version 충돌 | 동일 attempt/계획 명령에 한해 최신 버전 재접수, 서버 게이트 유지 / T-59, T-66 | initial-browser-02-failed → initial-browser-passed 및 현재 PASS | VERIFIED |
| REG-0004 | 시험 API bind 실패 후 기존 서버의 health를 성공으로 수용 | 사전 포트 확인, 새 runtime/키, 자식 프로세스 상태 확인 / 전체 UI runner | browser-failed 3 FAIL → 격리 재시험 3 PASS | VERIFIED |

RQ-14/15 입력 간소화와 RQ-28 데모 예외는 사용자 정책 변경이며 기존 필수 입력 계약을 버그로 기록하지 않는다. 새 정책의 방지 시험은 T-61~67이다.
