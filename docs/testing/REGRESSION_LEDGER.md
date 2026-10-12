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

## 후속 로컬 진입 검증

| ID | 재현 / 원인 | 수정 / 방지 시험 | 최초 실패 → 재시험 | 상태 |
|---|---|---|---|---|
| REG-0005 | 제거된 로그인 POST 경로를 무조건 404로 예상했으나 UI static mount가 있으면 405. 시험 기대값 오류 | T-68에서 정적 UI 유무에 따른 404/405 및 쿠키 미발급 확인. 다른 출처 차단 검증 유지 | backend-01: 86 PASS/1 FAIL → backend-02: 87 PASS | VERIFIED |

이번 수정 기준/실행별 결과/원문 출력은 [키 없는 진입 검증](runs/20261012-local-entry-agent-contract.md)에 있다. 첫 실패 당시 시험과 최종 수정 시험은 구분한다. D-38 접속 키 제거는 사용자 정책 변경이며 그 자체를 결함으로 기록하지 않는다. REG-0004의 시험 서버 식별은 새 runtime/키 방식에서 새 runtime/instance_id 대조로 갱신했고 UI 3개 PASS를 확인했다. 실제 운영 baseline은 미등록이다.

## 오케스트레이터 문서 확장

2026-10-12 D-39는 신규 설계이며 제품 코드 변경/결함 수정이 아니다. REG-0001~0005와 최초 FAIL·재시험 기록을 그대로 보존한다. T-71~85는 향후 회귀/인수 목록으로 추가했으며 아직 NOT_RUN이다. 실제 구현에서 결함이 재현되면 별도 REG와 실행 증거를 연결한다.

## 2026-10-12 M0 추가 확인

[Claude 패키지 실행](runs/20261012-claude-agent-package.md)에서 새 수동 계약의 ID/해시/권한/오래된 기준/UNKNOWN/덮어쓰기 거부 시험을 추가했다. 이 변경의 시험에서 발견되지 않은 결함을 새 REG로 만들지 않는다. 기존 REG-0001~0005와 최초 실패 기록은 그대로 유지하고 기존 기능 회귀를 함께 확인한다.

소스 기준/브리지 편의 변경은 T-92~95와 [20261012 실행](runs/20261012-settings-defaults.md)에 연결한다. 입력 편의 변경이 기존 job 기준이나 사용자 지정 명령을 바꾸지 않는 회귀 시험을 추가했다. 이번 시험 FAIL은 없고 기존 결함 이력은 유지한다.


## D-42 내장 연결 회귀

| ID | 재현 / 원인 | 수정 / 방지 시험 | 최초 실패 → 재시험 | 상태 |
|---|---|---|---|---|
| REG-0006 | 새 select/textarea의 중첩 텍스트가 정확한 label 탐색에 포함됨. 이전 REG-0002와 같은 유형이 새 필드에서 발생 | 명시 aria-label, 저장/재접속 T-101 및 고급 모드 T-95 | browser-initial/second → browser 최종 기록 | VERIFIED |
| REG-0007 | 브리지 추천 API 응답 중 workspace 편집 시 이전 workspace 기본 경로가 늦게 적용됨 | 응답 반영 때 현재 workspace로 기본값 정렬, 사용자 배열/현재 모드 보존 / T-95 | browser-second → browser 최종 기록 | VERIFIED |
| REG-0008 | 종료된 전경 프로세스의 회수한 PGID에 다시 killpg 호출, macOS 경계에서 PermissionError | 정상 종료 후 신호 생략. 종료 권한 실패면 UNKNOWN·잠금 유지 / T-100 | backend-process-failed → Python 217 PASS | VERIFIED |

실행별 최초 FAIL과 재시험은 [내장 연결 실행 기록](runs/20261012-native-cli.md)에 보존한다. 운영 baseline은 NONE이며 실제 Linux 인수와 구분한다.
