# GUI Test 실행·저장·어댑터 계약

현재 구현 기준: RQ-38~45 / D-43~46. 구현 위치 `gui_test/core/`, `gui_test/api/`, `gui_test/adapters/`. 실제 BCM/RBM/회사 TC/모델 과금 연결은 미구현이며 이 계약이 실환경 실행 권한을 부여하지 않는다.

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
