# GUI Test 실행·저장·어댑터 계약

현재 구현 기준: RQ-38~46 / D-43~47. 구현 위치 `gui_test/core/`, `gui_test/api/`, `gui_test/adapters/`, `gui_test/execution/`. Windows 공유 TC 실행 경로는 설정으로 활성화한다. 실제 BCM/RBM/회사 TC/모델 과금 인수는 미실행이며 이 계약이 실환경 실행 권한을 부여하지 않는다.

## 요청과 Suite

`POST /api/v1/gui-test/preflight`, `POST /api/v1/gui-test/runs`는 같은 StartRequest를 검증한다. 기존 `tc_ids`, `connection`, `source_revision`, `suite_revision`, `job_id`, `scenario`, `speed`, `execution`, `parent_run_id`에 다음 필드를 추가했다.

| 필드 | 기본 / 검증 | 의미 |
|---|---|---|
| tc_repeats | 빈 map; 선택된 TC ID만 허용; 값은 bool/string/float가 아닌 1~100 정수 | TC별 실행 횟수, 생략한 TC는1 |
| cycles | 정수1; 1~100 | 선택 목록 전체 반복 횟수 |
| command_profile | null 또는 저장된 프로파일 이름, 최대80자 | 기본 Mock 또는 공통 Single/Dual 명령 선택 |
| command_revision | 기본 빈 문자열, 최대64자 | 선택한 프로파일의 현재 해시와 일치해야 시작 가능 |

`cycles × sum(tc_repeats[id] 또는 1)`은 최대10,000이다. 중복 TC ID·필수 선행 순서·소스·Suite snapshot·Single/Dual 보드 검증은 기존대로 서버에서 수행한다. Suite 저장/불러오기에도 두 필드를 보존하며 과거 Suite는 모두1로 해석한다. 횟수/선택/순서 변경은 UI의 Suite 기준과 Preflight를 무효화한다.

명령 편집·프로파일 변경도 Preflight를 무효화한다. Run의 `command_snapshot`은 모든 반복 및 오류 복구에 동일하게 적용하고 Attempt의 `resolved_command_argv`와 Mock 로그에 치환 결과를 보존한다. 명령을 저장해도 실제 프로세스를 실행하지 않는다. 상세 변수·미리보기·저장 계약은 [명령 템플릿](../gui_test/COMMAND_TEMPLATES.md)을 따른다. 새 Retry/전체 재검증 Run에는 현재 확인한 명령 프로파일을 사용하며 원본 Run의 명령은 바꾸지 않는다.

## 실행 계획과 판정

시작 트랜잭션은 예약과 함께 불변 `plan`을 저장한다. plan 항목은 `tc_id`, `cycle`(전체 회차,1부터), `iteration`(해당 TC 반복 회차,1부터)이다. 예: A=2,B=1,cycles=2 → A,A,B,A,A,B.

- `index`는 다음/현재 plan 항목이다. `slot_results`는 문자열 index별 최신 판정이다.
- Attempt에 `slot_index`, `cycle`, `iteration`을 저장하고 `ordinal`은 TC별 실제 시도 수로 계속 증가한다.
- 오류·Timeout·UNKNOWN 복구는 현재 slot을 다시 시도한다. 과거 실패 Attempt는 보존하지만 같은 slot 복구 성공은 최신 판정으로 반영한다.
- 서로 다른 slot의 FAIL은 이후 성공으로 지우지 않는다. TC 결과는 모든 반복의 종합이며 진행률은 고정 plan의 PASS/FAIL 항목 수다. 아직 남은 slot이 있으면 취소의 전체 판정은 INCOMPLETE다.
- 전체 Run 최종 판정 후에만 Dashboard 동기화한다. 기존 이미지/매핑/선행 게이트와 예약 정책은 유지한다.

## 재실행

완료 FAIL 옆 Retry는 원본 `source_revision`, `connection_snapshot`, `parent_run_id`와 TC 하나로 새 Run을 생성한다. 횟수는1, Suite 기준은 비우고 Dashboard job은 연결하지 않는다. 원본 실패·로그·비용은 변경하지 않는다. 필수 선행 TC가 필요한 경우 단독 실행은 서버가 거부한다. 전체 재검증은 원본 TC 목록과 반복 계획을 사용한다.

## 모델 사용량

runner context의 `report_usage(sequence, rows)` 또는 최종 result의 `usage`가 누적 snapshot을 보고한다. 공개 시작 요청으로 사용량을 주입할 수 없다. 로그 문장을 파싱해 비용으로 만들지 않는다.

| rows 항목 | 검증 / 의미 |
|---|---|
| provider, model | 각각 비어 있지 않은 최대160자; 같은 쌍 중복 거부 |
| input_tokens, output_tokens | null 또는 bool이 아닌 0~10^15 정수 |
| cost_usd | null 또는 0~10^9의 유한 decimal 값; 내부에 decimal string으로 저장 |

한 snapshot은 모델 최대100개다. sequence는 0 이상 정수이고 이전·동일 sequence, 종료/다른 Attempt callback은 거부한다. snapshot을 더하지 않고 교체하며 최종 result는 최종 누적값이다. 비정상 보고는 마지막 유효 값을 보존한다. 모든 Attempt를 합산해 `progress.usage`의 모델 총합과 TC별 `cases`를 반환한다. null 비용은 0원으로 바꾸거나 모델 가격표로 추정하지 않는다. `[]`는 모델 호출 없음, 미제공은 집계 없음이고 일부 Attempt 누락은 partial이다.

## 실제 실행 대상

runner context의 `report_target(target)` 또는 최종 result의 `execution_target`을 사용한다.

- 로컬: `{"kind":"local"}`. 보드 목록이 있으면 거부한다.
- 보드: `kind=board`, `boards`에 `role`, `board_id`, `board_name`, `host`, `com`. Single은 a, Dual은 a/b 순서의 두 항목이다.
- board_id/host/COM은 고정된 connection과 정확히 일치해야 하며 보드 이름은 비어 있지 않은 최대160자/제어문자 없음이다. 같은 Attempt에서 다른 대상으로 덮어쓰지 않는다. 완료 후 callback은 거부한다.
- Attempt별 보고를 저장하고 Run 조회는 `execution_targets`, `targets_by_tc`의 labels/incomplete를 제공한다. 현재 UI 설정값이나 demo 보드 ID에서 실제 보드 이름을 추측하지 않는다.
- MockRunner는 실제 보드에 연결하지 않고 local과 모델 호출 없음만 보고한다. 실제 BCM/RBM 명칭/API는 후속 어댑터 구현 때 확인한다.

## 저장 호환성과 리포트

SQLite 테이블/schema_version=1은 유지하고 Run/Attempt/Suite JSON만 확장한다. plan 없는 과거 Run은 기존 TC별1회 경로로 읽고 복구한다. usage/target 없는 과거 Attempt는 미집계/기록 없음이다. 이전 데이터를 일괄 변환하거나 실패 기록을 삭제하지 않는다.

JSON/HTML/PDF/로그 ZIP은 전체 snapshot을 포함한다. CSV는 기존 판정 열에 Cycle/Repetition을 추가한다. 롤백 시 구버전 실행기는 새 반복 계획을 이해하지 못하므로 새 Run을 구버전 worker로 재개하지 않는다. 중단/완료와 백업을 확인한 뒤 해당 버전의 runtime을 별도로 복원한다.

[시험 목록](../testing/TEST_CATALOG.md) T-103~118, [게시 검증](../testing/runs/20261102-publication.md), [실환경 제약](../../gui_test/VALIDATION.md)을 함께 확인한다.

## Windows 실행기 계약 · RQ-46

Linux runtime의 `gui-test.json`에서 runner=windows-http와 loopback URL을 지정하면 기본 Mock 대신 WindowsRemote를 연결한다. API/worker 양쪽 환경변수 GUI_TEST_RUNNER_TOKEN을 사용한다. Windows 실행기는 같은 토큰을 검증하고 loopback/비브라우저 요청만 허용한다. SSH 역방향 터널은 배포 경로이며 public endpoint를 열지 않는다.

- GET /v1/catalog: Windows 공유 소스의 TC 목록·metadata·전체 파일 해시 revision. branch=shared.
- GET /v1/boards 및 POST /v1/verify: 운영자 설정 보드/COM과 Windows OS COM 열거 일치 검사. 보드 이미지 신원 증거가 아니다.
- POST /v1/executions: id(32자리 hex), tc_id, source_revision, connection, template. 첫 토큰 python/python3와 두 번째 {tc_path}만 실행 진입점으로 허용하며 두 이름 모두 Windows 설정의 고정 Python 절대 경로로 치환한다. PATH에서 python3를 검색하지 않는다. Windows에서 전체 소스를 검증·snapshot하고 COM argv를 치환한다. id와 payload hash를 영속화하고 중복은 같은 결과를 반환한다.
- GET /v1/executions/{id}: 영속 실행 상태. POST .../poll은 lease 갱신, .../cancel은 중단 요청. 응답은 id/request_hash/source_revision, RUNNING/DONE/UNKNOWN, stdout/stderr, exit_code/terminated/forced_state, 실제 argv다. Linux는 ID·요청 해시·소스 기준을 대조한다.
- 실행 전에 거부한 요청도 not_started tombstone을 저장한다. POST .../reconcile은 실행 기록이 없는 ID를 원자적으로 종료 확인 tombstone으로 고정하여 뒤늦은 시작을 막는다. 404나 네트워크 오류만으로 종료를 판단하지 않는다.
- Windows 프로세스 트리와 pipe EOF가 모두 확인된 뒤 최종 로그/종료 코드로 판정한다. 제한 초과·비정상 종료·불완전 근거는 ERROR/UNKNOWN. 로그는 메모리에서 제한·마스킹한 후 저장하며 raw 출력 파일을 만들지 않는다.
- Manager Attempt는 요청 시 resolved_command_argv를 유지하고 Windows가 실제 실행한 절대 Python/snapshot 경로는 executed_command_argv에 별도 기록한다. 실제 보드/이미지 증거가 없으므로 execution_target을 임의 생성하지 않는다.
- 기존 DB schema_version=1을 유지하고 실제 GUI Run은 gui-test-dashboard-windows/runs.db에 분리한다. 운영 Job 자동 반영은 비활성이다. Windows 실행기 DB/snapshot은 Windows runtime에 저장한다.

설정 예·한도·복구와 실환경 경계는 [Windows 실행기 안내](../gui_test/WINDOWS_RUNNER.md)를 따른다.

2026-11-03 확인 명령: Single `python3 {tc_path} -p {com_a}`(예: `python3 tc1.py -p COM7`). Dual `python3 {tc_path} -n {node_a} -n2 {node_b}`이며 사용자 예 노드명은 n295_sadk/n296_sadk다. Board에 선택적 node(1~160자, 영숫자 시작 후 영숫자/밑줄/점/하이픈)를 추가한다. node 미제공은 직렬화에서 생략하여 기존 snapshot/hash를 보존한다. Single은 com_a 한 번, Dual은 com_a/com_b 또는 node_a/node_b 쌍 각각 한 번이며 혼합/누락/중복을 거부한다. 노드명 명령은 두 노드명이 필수이고 Windows 등록 보드/COM/node와 정확히 일치해야 한다. 등록 노드명은 대소문자 무관 고유하며 실제 노드 접속 가능성을 입증하지 않는다. 기존 python 프로파일과 Mock 기본값은 보존한다.

진행 요약은 progress.done/total(반복 포함 PASS/FAIL 판정 횟수)과 모델별 cost_usd 합계를 표시한다. 일부 미보고 또는 null 비용은 일부 미집계, 전부 미보고는 미집계, 보고된0은 $0으로 구분한다. Run/TC별 상세는 기본 접힘이며 보고값과 원본 이력을 바꾸지 않는다.

## D-48 별도 자동 퓨징 파이프라인

일반 GUI Run의 운영 Job 자동 완료 제한은 유지한다. 별도 서버 HardwareCoordinator/Windows FlashService가 동일 BSP Attempt에 퓨징·부팅·TC 증거를 연결하는 opt-in 경로를 추가했다. 기존 GUI Test 실행과 Windows 예약을 공유하되 TC용10초 lease 중단 정책을 퓨징에 적용하지 않는다. 요청/상태/설정 필드의 기준은 [자동 퓨징 계약](AUTOMATIC_FLASH_TEST.md)이다.


## 실제 연결 보기 · D-50

기존 /api/v1/gui-test 경로를 보존하고 /api/v1/gui-test/live를 추가한다. 실제 manager는 재사용하며 미설정이면 gui-test-<mode>-windows/runs.db의 조회·프로파일 저장용 manager만 만든다. 별도 worker를 생성하지 않는다. capabilities.connection은 state(unconfigured/disconnected/connected), ready, message를 제공한다. connected는 인증된 identity 응답이며 보드·이미지 검증 성공이 아니다. 미연결 시 catalog/boards는 빈 목록, preflight/start/resume/recover는 503이다. pause/cancel/제어권 조작은 기존 manager 검증을 거쳐 로컬 의도를 기록한다. Mock 데이터는 복사하지 않는다. 설정 반영은 API/worker 재시작이 필요하며 단독 서버의 원격 실제 실행 제한을 유지한다.
