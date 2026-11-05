# BSP 모듈의 TC 목록 준비 계약 · RQ-53

Ethernet 등 영속 BSP 모듈이 장비 테스트 단계에 들어가면 그 모듈의 TC만 준비한다. 이 기능은 목록 준비·선택 범위 검증이며 새 Run을 자동으로 시작하거나 BSP 모듈을 완료하지 않는다. 기본 수동 시험, 최초 계획/선행 그룹/의존 게이트와 최종 사람 검토를 유지한다. 기존 D-48 자동 퓨징 프로파일의 실행 소유권은 별도다.

## 모듈 소속과 순서

TC 카탈로그의 기존 `module`은 폴더 경로 의미를 유지한다. 소스 metadata에 선택적 `modules: string[]`를 제공할 수 있다. 값은 비어 있지 않은 최대 100개의 모듈 이름이며 이름은 1~160자, 제어문자·정규화 후 중복을 허용하지 않는다. 명시적 소속이 있으면 경로보다 우선하고 잘못된 값은 TC를 비활성화하며 경로 검색으로 대체하지 않는다.

명시적 소속이 없는 TC는 경로 각 구성 요소와 Python 파일명에서 NFKC·대소문자 정규화한 모듈 이름 토큰을 찾는다. `Ethernet/01_link.py`, `ethernet_test.py`는 Ethernet과 일치하지만 `notethernet.py`, `network`, `net`을 임의 별칭으로 간주하지 않는다. 다단어 모듈 이름은 연속된 전체 토큰으로 일치한다.

대상 ID는 중복을 제거하고 `after`를 안정적인 위상 정렬로 배치한다. 실행 불가 TC, ID 중복, 잘못된 소속/선행 조건, 없는 선행 TC, 다른 모듈·명시 매핑 밖 선행 TC, 순환, 0개 일치는 이유를 반환한다. 모든 TC로 자동 대체하거나 다른 모듈의 선행 TC를 임의로 추가하지 않는다. 서버가 관리하는 D-48 `cases`의 명시 목록은 이름·경로 검색보다 우선한다.

## 조회

`GET /api/v1/gui-test[/live]/module-selection?job_id=…&module_id=…&branch=…&catalog_revision=…`

`job_id/module_id`는 운영 BSP의 영속 식별자다. 서비스는 Engine snapshot → 카탈로그 해석 → Engine snapshot 재확인 순서로 읽고 중간 작업 버전 변경이나 요청한 카탈로그 기준 변경은 409로 거부한다. 실제 BSP 작업에 Mock 카탈로그를 제시하지 않는다. 단독 GUI에서는 BSP 모듈 조회를 422로 거부한다.

| 응답 | 의미 |
|---|---|
| context | `job_id`, `module_id`, `attempt_id`, `plan_version`, `fingerprint`, `catalog_revision`의 고정 기준. 테스트 시도 전에는 attempt_id가 null이고 실행 불가 |
| module_name, module_status | 영속 모듈 이름과 현재 device_test 상태 |
| mode | `manual` 또는 `automatic`. automatic은 일반 Run 시작 불가 |
| blocked_reason | 실행·목록 적용이 불가한 이유. 적용 가능한 manual 입력 대기 상태만 null |
| tests, tc_ids | 해당 모듈에 속한, 선행 순서로 정렬한 후보만 반환. 전체 카탈로그가 아님 |
| catalog_revision | 이 목록의 실제 TC 소스 기준 |
| frozen | 배정된 D-48 payload의 동결 목록이면 true. 현재 카탈로그와 다른 기준도 읽기 전용 표시 가능 |

입력 대기 전, gate 대기, 연결 실패, 잘못된 매핑은 200 응답의 `blocked_reason`으로 표시할 수 있다. 소속이 불분명한 목록을 실행 가능한 결과로 승격하지 않는다. 프론트엔드는 활성 Test 화면에서만 조회하고 오래된 요청 응답·다른 모듈/시도의 목록을 적용하지 않는다. 수동 선택·설정·과거 Run을 새 조회마다 덮어쓰지 않는다.

## D-48 소유권

`device-test.json`은 HardwareWorker와 마찬가지로 서비스 시작 때 읽는다. bridge 작업의 해당 모듈 프로파일이 활성이고 장비 테스트가 입력 대기 또는 실행 중이면 자동 경로가 소유한다. 필수 사례의 `cases` 매핑으로 후보를 준비하고 일반 Run으로 중복 시작하지 않는다. 설정이 잘못돼도 수동 경로로 우회하지 않는다. 명시적으로 비활성인 기존 설정은 수동 기본값을 유지한다.

`stage.automation`이 있으면 설정 파일의 현재 활성 여부와 무관하게 자동 경로가 소유한다. `automation.payload.tests/cases/source_revision`을 동결 목록으로 표시하며 현재 카탈로그의 다른 TC로 교체하지 않는다. 저장된 구성 자체가 불완전하면 실행 불가 이유를 표시한다.

시작 때 읽은 설정과 현재 파일의 해시가 다르거나 파일을 읽을 수 없으면 실제 모듈의 새 목록 적용·일반 실행을 막고 API와 worker의 동시 재시작을 요구한다. **API만 새 설정으로 재시작하고 worker를 이전 설정으로 남긴 경우까지 탐지하는 공통 config registry는 없다.** 두 프로세스를 함께 재시작하는 기존 운영 선행 조건을 유지한다. 이 기능은 프로파일을 활성화하거나 설정 파일을 쓰지 않는다.

## Preflight와 시작

`StartRequest`에 선택적 엄격한 `module_context`를 추가한다. 6개 기준 필드는 모두 필수이고 계획 버전은 1 이상의 엄격한 정수다. 컨텍스트가 없으면 직렬화에서 필드를 생략해 기존 요청과 명령 해시를 보존한다. 기존 `job_id`는 격리 Demo 결과 연결용이며 운영 `module_context`와 혼합하면 422로 거부한다.

Preflight와 신규 시작은 최신 attempt·plan·fingerprint·catalog, 입력 대기 상태, 기존 gate, 자동 소유권, TC 범위와 선행 조건을 서버에서 재검사한다. 수동 후보의 일부 선택은 허용하지만 다른 모듈 TC를 추가하거나 필수 선행 순서를 생략할 수 없다. 자동 소유권은 403 `AUTOMATIC_TEST_OWNED`, 오래된 기준은 409 `MODULE_CONTEXT_CHANGED`, 범위 밖 TC는 422 `MODULE_TC_MISMATCH`로 거부한다.

원격 카탈로그·보드·명령 준비는 BSP 쓰기 잠금을 잡기 전에 끝낸다. 신규 Run 기록 직전 주입된 서비스 guard가 BSP DB의 `BEGIN IMMEDIATE` 안에서 현재 기준·gate·자동 소유권을 빠르게 재검사한다. GUI의 Run·장비 예약·명령 원장이 commit될 때까지 그 guard를 유지해 동시에 자동 배정되는 경합을 막는다. 두 DB를 하나로 합치거나 새 BSP 결과를 쓰지 않는다. 동일 명령의 저장된 응답은 준비·guard 전에 반환하며 기존 멱등 동작을 유지한다.

핵심 구현은 `backend/gui_test/core/module_selection.py`, `backend/services/module_test_selection.py`와 Manager의 선택적 서비스 주입이다. core는 Dashboard 서비스 구현을 import하지 않는다. 서버 주입이 없는 단독 환경은 컨텍스트 요청을 거부한다. 새 Run에 해당 컨텍스트를 보존하지만 기존 운영 Job 자동 완료 연결로 사용하지 않는다.

Git HEAD는 조회 참고 정보이며 이 문서의 `catalog_revision`과 다르다. `shared-*`/`content-*` 파일 스냅샷 기준과 Git 메타데이터의 관계는 [GUI Test 계약](GUI_TEST_CONTRACT.md)을 따른다. 검증은 T-163과 기존 GUI·Preflight·D-48 회귀를 사용하고 실제 BSP·장비 인수는 별도다.
