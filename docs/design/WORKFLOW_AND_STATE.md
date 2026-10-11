# 실행 순서·상태·진행률

## 실행 순서

1. Start 접수: 설정·접근·소스 기준·도구 기능 점검 → job 및 command 저장 → Claude 조정 세션 연결.
2. 초기 모듈 제안과 벤더 변경 목록을 영속 저장. 모든 모듈 분석을 고정 입력으로 병렬 배정한다.
3. 필수 분석이 끝나면 모듈 목록·선행 그룹·변경 계획·시험 범위를 plan_version과 함께 최초 확인받는다. 미분류 판단은 영향 범위를 드러내고 확인 가능 여부를 판정한다.
4. 확인된 선행 그룹부터 설계 → 코드와 리뷰 → 빌드 → 검증 → 수동 장비 시험을 진행한다. 그룹 내부의 산출물 의존성도 검사한다.
5. 선행 그룹의 필수 결과와 관련 판단이 모두 유효하게 완료되면 나머지 모듈의 설계 이후를 허용한다. 수정·빌드는 공유 배타 큐로 실행한다.
6. 모듈 검증에 필요한 이미지는 해당 변경이 준비되는 시점에 만든다. 그 이미지로 수행할 장비 시험의 완료를 이미지 생성 조건으로 삼지 않는다.
7. 최종 통합 기준 빌드 → 필수 회귀 검증 → 벤더 변경 누락 확인 → 최종 사람 검토 → 전체 완료.

## 상태 모델

실행 상태와 결과 유효성을 분리한다. 과거 성공 시도는 SUCCESS를 유지하면서 현재 결과의 validity만 INVALIDATED로 바뀔 수 있다.

| 대상 | 상태 | 의미 |
|---|---|---|
| Job | CREATED / ANALYZING / AWAITING_PLAN_CONFIRMATION / RUNNING / AWAITING_FINAL_REVIEW / COMPLETED / CANCELLED | 전체 수명주기. 실패·차단·불명 개수는 별도 health로 집계 |
| Work item | PENDING / BLOCKED / READY / QUEUED / RUNNING / WAITING_INPUT / SUCCEEDED / FAILED / CANCELLED / UNKNOWN / NOT_APPLICABLE | 현재 필요한 작업의 상태 |
| Attempt | CREATED / DISPATCHING / RUNNING / CANCEL_REQUESTED / SUCCEEDED / FAILED / CANCELLED / UNKNOWN | 실제 실행 회차. 종료 기록 불변 |
| Result validity | CURRENT / INVALIDATED / UNVERIFIED | 현재 입력에 대한 결과 사용 가능 여부 |
| Health | OK / DEGRADED / BLOCKED / UNKNOWN | 독립 작업이 실행 중이어도 다른 모듈 실패를 숨기지 않음 |

`WAITING_INPUT`에는 수동 시험 제출·사람 판단·리뷰 대기를 reason_code로 구분한다. 연결 끊김은 UI 연결 상태이며 attempt FAILED와 다르다. N/A는 사유·결정 범위·버전이 있는 제외 기록으로만 설정한다.

### 전이 규칙

- PENDING/BLOCKED → READY: 현재 계획, 의존 결과, 사람 결정, 환경 조건 만족.
- READY → QUEUED → RUNNING: 명령 접수·잠금/실행 토큰 확보·프로세스 식별자 기록 후 전이.
- RUNNING → SUCCEEDED: 종료 코드뿐 아니라 구조화 결과, 필수 증거, 입력 fingerprint 일치 확인.
- RUNNING → FAILED: 확인된 실패와 원인 분류. 관찰 중단은 UNKNOWN으로 전이.
- RUNNING → CANCEL_REQUESTED → CANCELLED: 실제 프로세스 종료 확인 후 자원 해제. 취소 버튼 접수만으로 종료 처리하지 않는다.
- FAILED/CANCELLED → READY: 명시적 재시도/재개 명령과 게이트 재검사. 새 attempt를 생성하며 이전 것을 수정하지 않는다.
- UNKNOWN → 관찰된 상태: 외부 프로세스/세션 조회로 확정. 확인 전 재실행 금지.
- SUCCEEDED + 입력 변경: 과거 attempt 보존, 결과 INVALIDATED, 작업은 재실행 필요로 표시. 필요한 후속 결과도 연쇄 무효화.

## 게이트 판정

분석 작업: 환경/소스 준비만 요구하며 최초 계획 확인·선행 완료를 요구하지 않는다.

설계 이후 작업: 최초 확인된 현재 계획 + 단계 선행 결과 + 미해결 의존 판단 없음. 나머지 그룹이면 추가로 **선행 그룹 전체 완료**가 필요하다. 같은 정책을 Start, 자동 배정, 프롬프트, 재시도 모두에 적용한다. UI 비활성화만으로 보호하지 않는다.

모듈 완료는 필수 단계 CURRENT 성공/승인된 N/A와 필수 결정 반영을 확인한다. 부트로더 코드 완료나 반올림 100%로 게이트를 열지 않는다. 선행 그룹이 비어 있으면 사용자 확인된 “선행 없음” 계획이 있어야 한다.

선행 결과가 나중에 무효화되면 후속 신규 배정 중지, 실행 중 작업에는 안전 중단/결과 보류 정책을 적용한다. 하위 결과를 현재 완료로 인정하지 않는다. 중단 가능한 지점과 보존할 산출물을 어댑터별로 정의한다.

## 잠금과 재시작

- 자원 키는 작업 ID가 아니라 실제 공유 작업 공간 ID다. 여러 upgrade job도 같은 작업 사본을 쓰면 경합한다.
- DB 트랜잭션에서 실행 가능성 검사, 유일 active attempt 확보, 자원 lease와 증가하는 fencing token 기록을 함께 처리한다.
- 프로세스 시작 전 DISPATCHING intent를 저장하고 실행 식별자를 회수한다. 그 사이 장애는 reconciler가 확인한다. 지원 도구가 식별/조회 불가이면 UNKNOWN 유지 후 운영 확인을 요구한다.
- heartbeat 만료는 소유권 의심 신호다. 이전 프로세스 종료가 확인되기 전 새 writer를 시작하지 않는다. 늦은 결과는 attempt/token/fingerprint가 맞아야 적용한다.
- 일시 중지는 신규 배정을 막는다. 취소는 해당 실행 중지를 요청한다. 둘을 혼용하지 않는다.

## 진행률 기준안 ADR-02

각 계획 버전에 적용 대상 필수 leaf work unit과 weight를 고정한다. 초기 weight=1. 분석은 모듈당 분석 결과 1, 설계 1, 코드+리뷰 완료 1, 빌드 1, 검증은 필수 사례별 1, 장비 시험은 필수 사례별 1을 기준으로 제안한다. 부모 단계와 하위 시험을 동시에 세지 않는다. 실제 사례 목록이 없으면 해당 집계는 “산정 중”이다.

`percentage = 100 × sum(weight of CURRENT successful units) / sum(weight of applicable required units)`

- 상단 매핑: 분석=analysis, 구현=design+code, 검증=verification, 빌드=build, 테스트=device_test. 화면 표시 순서와 실행 순서는 별개다.
- 선행 대기·실패·리뷰 대기·재검증 필요는 분모에 있고 분자에는 없다. 진행 중 임의 50%를 추가하지 않는다.
- 승인된 N/A만 분모 제외. 분모 0은 “해당 없음”. 작업 정의 전은 “산정 중”. 실제 완료 전 표시 반올림으로 100%가 되지 않게 한다.
- 전체는 고유 unit ID로 초기 기준 준비, 최초 계획 확인, 모듈 작업, 통합 빌드·회귀, 최종 검토를 합산한다. 상단 5개나 그룹 비율의 평균을 쓰지 않는다.
- 최종 검토 전 전체 100% 금지. 분석 전용 실행 범위 완료는 전체 업그레이드 완료와 별도 표시한다.
- 계획 변경/결과 무효화로 진행률이 내려가면 이전 값·사유·기준 버전을 보여준다.

진행률은 시간 추정치가 아니다. 이 단위·가중치는 기술 기준안으로 기록하며 사용자 확정 정책으로 표현하지 않는다.

## 2026-10-12 확정 변경

수동시험은 사례별 PASS/FAIL만 사용자 필수 입력으로 받고 현재 이미지/소스/계획과 등록 시각은 자동 기록한다. 미입력한 보드·수행자·수행 시각·근거는 완료를 막지 않는다. 입력된 잘못된 선택값과 오래된 attempt는 거부한다.

데모의 선행 모듈에 한해 최초 계획 확인 후 남은 단계를 수동 모의 완료할 수 있다. 관련 판단 대기와 일시 중지를 유지하며 실제 실행에서는 금지한다. 기존 실패는 유지, 진행 중 데모 attempt는 CANCELLED로 보존, 해당 attempt의 잠금만 해제하고 새 모의 완료 attempt를 생성한다. 늦은 결과는 최신 attempt/token 불일치로 거부한다. 그룹 전체 완료 전에는 나머지 설계 이후가 계속 잠긴다.
