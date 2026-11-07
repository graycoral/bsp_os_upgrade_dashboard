# GUI Test 실행·저장·어댑터 계약

현재 구현 기준: RQ-38~46 / D-43~47. 구현 위치 `backend/gui_test/core/`, `backend/gui_test/api/`, `backend/gui_test/adapters/`, `backend/gui_test/execution/`. Windows 공유 TC 실행 경로는 설정으로 활성화한다. 실제 BCM/RBM/회사 TC/모델 과금 인수는 미실행이며 이 계약이 실환경 실행 권한을 부여하지 않는다.

RQ-54/D-57의 소스 배치·빌드·설치 경계는 [GUI Test 구조 계약](GUI_TEST_LAYOUT.md)을 따른다. 단독 앱은 `apps/gui-test/`, 공유 UI는 `packages/gui-test-ui/src/`다. 아래 API·요청·보고 필드와 DB/runtime 계약은 구조 변경으로 바뀌지 않는다. 소스 import `backend.gui_test.*`와 설치 wheel의 `gui_test.*`를 구분한다.

## 요청과 Suite

운영 BSP 모듈의 TC 자동 목록 준비와 선택적 `module_context`는 [모듈 TC 선택 계약](MODULE_TC_SELECTION.md)을 따른다. 기존 격리 Demo 연결용 `job_id`와 운영 컨텍스트는 혼합하지 않으며, 목록 준비가 실제 장비 실행이나 모듈 완료를 뜻하지 않는다.

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

[시험 목록](../testing/TEST_CATALOG.md) T-103~118, [게시 검증](../testing/runs/20261102-publication.md), [실환경 제약](../../apps/gui-test/VALIDATION.md)을 함께 확인한다.

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

### 선택적 TC 소스 Git 정보

Windows 실행기의 `GET /v1/catalog`와 이를 전달하는 Dashboard 카탈로그는 선택적 `git` 객체를 제공한다. 기존 실행기가 이 필드를 생략해도 호환된다. Mock·미연결 카탈로그에 Git 정보를 만들어 넣지 않는다.

| 필드 | 의미 |
|---|---|
| status | `available`, `not_repository`, `git_unavailable`, `timeout`, `error`, `unborn` 중 하나 |
| source_path, repository_path | 설정된 원본 TC 폴더의 절대 경로와 그 폴더가 실제 속한 Git 작업 트리 경로. 미확인은 null |
| remote | 로컬 `origin` 설정에서 확인한 원격 주소. URL 사용자 정보·query·fragment와 SCP형 사용자 이름을 제거하며 미설정·인식 불가 형식은 null |
| branch, commit | 조회 시점의 실제 HEAD 브랜치와 전체 커밋 ID. 미확인은 null. 빈 저장소는 `unborn`이고 commit은 null |
| detached | detached HEAD이면 true, 확인된 브랜치 HEAD이면 false, 미확인은 null. detached 상태도 커밋을 확인하면 `available` |
| checked_at | UTC 조회 시각(ISO 8601) |

조회는 Windows Host의 설정된 원본 TC 폴더에서만 수행한다. 임시 스냅샷이나 Dashboard 개발 저장소로 대체하지 않는다. 고정 인자의 읽기 전용 Git 명령에 약 2초의 전체 제한과 출력 크기 제한을 적용하며 상속된 Git 경로·설정 환경변수는 제거한다. 네트워크·checkout·pull·쓰기 명령은 실행하지 않고 원문 stderr·인증정보를 응답이나 로그에 남기지 않는다. Git 조회 실패는 TC 카탈로그 실패로 확대하지 않는다.

`catalog.branch=shared`와 파일·metadata 해시인 `revision`은 그대로다. Git HEAD는 조회 당시 참고 정보이며 실행 파일 동일성의 증거가 아니다. `git` 객체를 스냅샷 해시·Suite·Preflight·실행 요청에 넣지 않는다. UI는 TC 소스 Git과 TC 스냅샷 기준을 구분하고, 구 실행기 응답은 ‘Git 정보 미제공’, 연결 전은 ‘실행기 미연결 · 미확인’, Mock은 ‘모의 소스’로 표시한다.

2026-11-03 확인 명령: Single `python3 {tc_path} -p {com_a}`(예: `python3 tc1.py -p COM7`). Dual `python3 {tc_path} -n {node_a} -n2 {node_b}`이며 사용자 예 노드명은 n295_sadk/n296_sadk다. Board에 선택적 node(1~160자, 영숫자 시작 후 영숫자/밑줄/점/하이픈)를 추가한다. node 미제공은 직렬화에서 생략하여 기존 snapshot/hash를 보존한다. Single은 com_a 한 번, Dual은 com_a/com_b 또는 node_a/node_b 쌍 각각 한 번이며 혼합/누락/중복을 거부한다. 노드명 명령은 두 노드명이 필수이고 Windows 등록 보드/COM/node와 정확히 일치해야 한다. 등록 노드명은 대소문자 무관 고유하며 실제 노드 접속 가능성을 입증하지 않는다. 기존 python 프로파일과 Mock 기본값은 보존한다.

진행 요약은 progress.done/total(반복 포함 PASS/FAIL 판정 횟수)과 모델별 cost_usd 합계를 표시한다. 일부 미보고 또는 null 비용은 일부 미집계, 전부 미보고는 미집계, 보고된0은 $0으로 구분한다. Run/TC별 상세는 기본 접힘이며 보고값과 원본 이력을 바꾸지 않는다.

## D-48 별도 자동 퓨징 파이프라인

일반 GUI Run의 운영 Job 자동 완료 제한은 유지한다. 별도 서버 HardwareCoordinator/Windows FlashService가 동일 BSP Attempt에 퓨징·부팅·TC 증거를 연결하는 opt-in 경로를 추가했다. 기존 GUI Test 실행과 Windows 예약을 공유하되 TC용10초 lease 중단 정책을 퓨징에 적용하지 않는다. 요청/상태/설정 필드의 기준은 [자동 퓨징 계약](AUTOMATIC_FLASH_TEST.md)이다.


## 실제 연결 보기 · D-50

기존 /api/v1/gui-test 경로를 보존하고 /api/v1/gui-test/live를 추가한다. 실제 manager는 재사용하며 미설정이면 gui-test-<mode>-windows/runs.db의 조회·프로파일 저장용 manager만 만든다. 별도 worker를 생성하지 않는다. capabilities.connection은 state(unconfigured/disconnected/connected), ready, message를 제공한다. connected는 인증된 identity 응답이며 보드·이미지 검증 성공이 아니다. 미연결 시 catalog/boards는 빈 목록, preflight/start/resume/recover는 503이다. pause/cancel/제어권 조작은 기존 manager 검증을 거쳐 로컬 의도를 기록한다. Mock 데이터는 복사하지 않는다. 설정 반영은 API/worker 재시작이 필요하며 단독 서버의 원격 실제 실행 제한을 유지한다.

보기 모드는 통합 화면의 환경 설정에서 선택·적용한다. 단독 화면은 내부 설정에서 같은 선택을 제공한다. Test 현황의 결과 화면에는 전환 버튼을 중복 표시하지 않는다. URL `guiExecution`과 브라우저 저장 선호를 유지하며 전환이 기존 Run을 중단하거나 이력을 복사하지 않는다. 실행기 미설정·미연결 안내는 `connection.ready`가 false일 때만 기본 접힘으로 표시하고 연결이 확인되면 숨긴다. 실행 차단과 서버 연결 검증은 접힘 상태와 무관하게 유지한다.

## TC 목록 읽기 설정 · RQ-58 / D-62

두 prefix `/api/v1/gui-test`와 `/api/v1/gui-test/live`에 `GET /source/request-settings`와 `PUT /source/request-settings`를 제공한다. 응답과 PUT 본문은 `{ "catalog_timeout_seconds": 100 }`이며 boolean·문자열·실수·누락·추가 필드 및 1~600 범위 밖 값은 거부한다. 설정 API는 Runner 연결 확인이나 카탈로그 읽기를 호출하지 않으며 목록 로딩 실패·미연결 중에도 사용할 수 있다.

`CatalogSettings(path)`는 표준 라이브러리만 사용한다. `read()`는 파일 부재 시 기본 100을 반환하고 저장된 값은 엄격히 검증한다. `save(int)`는 검증 후 임시 파일을 flush/fsync하고 replace하여 저장한다. 잘못된 입력이나 저장 실패는 이전 설정 파일을 보존한다. 공통 runtime factory는 `<runtime>/gui-test-settings.json`을 normal/live·API·worker에 공유하며, 직접 생성한 Manager는 DB 옆의 같은 파일명을 기본으로 사용한다. 연결 URL/토큰 파일과 DB schema_version=1은 바꾸지 않는다.

각 `WindowsRemote.catalog()`는 공급 callable에서 유효값을 한 번 읽고 해당 `/v1/catalog` 요청에만 적용한다. 저장 후 다음 요청부터 변경값을 사용하고 진행 중 요청은 읽어 둔 값을 사용한다. 공통 HTTP 클라이언트 5초, identity·boards·실행 제어·lease·TC 실행 시간은 유지한다. 실제 HTTP timeout만 `TC_CATALOG_TIMEOUT`/504와 유효 초를 포함한 안내로 변환하며 인증 거부·네트워크 오류를 timeout으로 표시하지 않는다. HTTP timeout은 각 네트워크 작업의 대기 제한이며 목록 서버의 실행 취소나 전체 작업의 wall-clock 보장은 아니다.

설정 저장은 소스 version/revision·선택·반복·Suite·Preflight·Run을 변경하지 않는다. 새 설정은 legacy Windows 공유 목록의 호출 대기를 조정하며 서버 폴더/Git inspect/apply의 시간 제한을 변경하지 않는다. 구 Runner의 기존 catalog 서버와 호환하며 `source_snapshot_v1` 지원 여부에는 영향을 주지 않는다. 승인된 기존 EXE는 갱신하지 않는다. [마법사 사용](../gui_test/SETUP_WIZARD.md), [이식](../porting/PORT-005.md), [시험 상태](../testing/runs/20261106-catalog-timeout.md).

## TC 소스 등록과 고정 실행 · RQ-56 / D-60

두 API prefix `/api/v1/gui-test`와 `/api/v1/gui-test/live`에 같은 계약을 제공한다. 저장소의 실제 원본은 읽기 전용이며, 새 소스는 서버의 해당 GUI workspace DB 옆 `source-storage/snapshots/<snapshot_id>`에 준비한 고정 파일로 목록과 실행을 연결한다. Mock/실제 workspace는 기존 DB 분리를 유지한다. 실행기 연결 없이 등록·목록 조회·Suite 저장이 가능하고 실제 실행은 기존 연결·COM·명령 검증을 통과해야 한다.

| API | 요청 / 응답 |
|---|---|
| GET /source | `version` 정수, `active`, `execution` |
| POST /source/inspect | `{kind,location}` → `{inspection_id,kind,location,repository,refs,default_ref,inspected_at}` |
| PUT /source | `{inspection_id,ref,expected_version}` → GET 응답과 적용된 `catalog` |

`active`는 `kind`(`legacy`, `server-folder`, `git-url`), `location`, nullable `ref`, `commit`, `inspection_id`, `snapshot_id`, `source_revision`이다. 초기 상태는 version0, legacy, 빈 location, 나머지 null이다. `execution`은 `{ready,reason,code}`이며 code는 `READY`, `RUNNER_UNAVAILABLE`, `SOURCE_SNAPSHOT_UNSUPPORTED`다. Mock은 READY이며 실제 연결은 인증된 identity를 확인한다. 새 소스의 실제 실행에는 identity의 `source_snapshot_v1:true`가 필요하다. 구 실행기로 자동 대체하지 않는다.

inspect는 실제 Git branch만 `refs:[{name,ref,commit}]`으로 반환한다. ref는 `refs/heads/main`처럼 전체 이름이고 commit은 전체 object ID다. plain folder는 repository=false, refs=[], default_ref=null, apply ref=null이다. `legacy`/빈 location 검사 후 apply하면 기존 소스로 돌아가며 version은 증가한다. legacy 카탈로그는 기존 demo/shared 경로로 읽고 미연결 live는 빈 목록을 유지한다.

- server-folder는 서버에서 접근 가능한 절대 디렉터리다. Git 작업 트리 안의 폴더는 해당 committed subtree를 읽고 작업 트리 수정·checkout을 하지 않는다. bare repository도 지원한다. plain folder는 apply 시점의 현재 파일을 고정한다.
- git-url은 HTTPS 또는 `ssh://user@host:port/project` 형식이다. Gerrit의 SSH 포트를 지원한다. HTTP/file/ext/SCP 축약 주소·HTTPS userinfo·비밀번호·query·fragment를 거부한다. inspect는 ls-remote의 실제 heads와 기본 ref를 읽으며 apply는 관리 임시 bare 저장소로 선택 ref를 fetch하고 inspect commit과 다르면 거부한다. 원본 최신 커밋을 조용히 적용하지 않는다.
- 인증은 서버 서비스 계정의 SSH agent/기본 키·SSH config/known_hosts 또는 사전에 설정한 사용자 global Git credential helper를 사용한다. 시스템 Git config와 상속 GIT_* override/trace/askpass는 사용하지 않으며 SSH는 BatchMode/StrictHostKeyChecking이다. 대화형 인증은 지원하지 않는다. 원문 Git stderr·비밀 값을 응답/로그에 넣지 않는다.
- 숨김 파일 및 기존 실행기 제외 디렉터리는 기존 소스 수집 규칙으로 제외한다. 링크·submodule·외부 파일 참조는 snapshot에 포함하지 않는다. 수집 대상 링크/submodule은 거부한다. 최대10,000개 파일, 전체128MiB, 파일별16MiB이며 Windows에서 안전한 상대 경로와 대소문자 고유성을 요구한다. 외부 Python/TC 패키지는 기존 실행기 환경에 별도로 설치되어 있어야 한다.
- metadata는 새 소스에서 `{}`이며 `discover(snapshot,{})`의 기본값을 적용한다. 임의 metadata 파일 이름을 추측하지 않는다. manifest의 source identity(종류·위치·검사 ID·ref·commit·generation), 파일 크기/SHA-256, metadata를 포함해 source_revision/snapshot_id를 계산한다. 같은 파일로 소스를 다시 적용해도 기준이 바뀐다.

DB schema_version=1을 유지하고 documents의 내부 source-state/source-inspection 문서만 추가한다. 읽기·Git·복사·해시는 쓰기 transaction 밖에서 준비하고 apply의 마지막 transaction에서 expected_version을 다시 비교해 active pointer만 교체한다. 실패·오래된 적용은 이전 선택을 보존한다. 준비했으나 CAS에서 지는 스냅샷은 보존하며 자동 정리하지 않는다.

새 Run은 공개 경로가 없는 `source_snapshot:{version,snapshot_id,source_revision}`을 저장한다. Preflight 이후 실제 Run 예약 transaction에서 generation과 revision을 다시 비교한다. worker는 이 descriptor로 서버 내부 디렉터리를 찾아 실행기에 전송한다. 이후 소스 선택이 바뀌어도 실행 중인 Run은 원래 스냅샷을 사용한다. 필드가 없는 과거 Run은 기존 경로다. 새 소스 Suite 저장의 data.source_revision은 필수이고 현재 revision과 일치해야 한다. legacy는 생략을 허용하며, Suite 저장도 마지막 transaction에서 source generation을 재확인한다.

### Windows source_snapshot_v1 전송

인증된 `PUT /v1/source-snapshots/{snapshot_id}`의 Content-Type은 application/zip이다. 해당 경로만 최대160MiB의 disk 임시 스트림을 받고, 나머지 요청의 기존64KiB 제한은 유지한다. 수신·검증·게시에는 실행 DB transaction/COM lock을 잡지 않는다. archive는 ZIP_STORED만 허용한다.

archive의 `.source-manifest.json`(최대4MiB)은 `{format:'source_snapshot_v1',source,metadata:{},files:{relative_path:{size,sha256}},source_revision,snapshot_id}`다. source_revision은 `source-`와 format/source/metadata/files의 canonical digest이며 snapshot_id는 그 객체에 source_revision을 더한 digest다. canonical digest는 기존 `models.digest`의 sort_keys/ensure_ascii=False JSON SHA-256이다. 파일 전체와 manifest identity를 재검증한다. 절대/상위/빈/역슬래시/ADS 경로, Windows 예약 이름·끝 공백/점·제어문자, 대소문자 중복·파일/디렉터리 충돌, 링크·비정규 ZIP member, 암호화·압축·예상 밖 member, 크기 제한 초과를 거부한다.

검증 완료 후 snapshot ID 디렉터리를 원자적으로 게시한다. 게시 후 최종 경로의 manifest와 파일 바이트를 다시 읽어 확인한 뒤에만 성공을 반환하고 active pointer를 저장한다. Windows 내부 snapshot I/O는 UNC를 포함하는 Win32 extended path를 사용해, 짧은 임시 경로에서 긴 snapshot ID 경로로 rename한 후 MAX_PATH 때문에 파일을 읽지 못하는 성공 오인을 방지한다. 같은 ID/내용의 재전송은 멱등이며 기존 내용도 다시 확인한다. `POST /v1/executions`는 선택적 `snapshot_id`를 추가하고, 있으면 준비한 스냅샷을 실행별 writable directory로 복사한 뒤 바이트·revision을 검증하고 실행한다. `Host.root`와 `WindowsRemote.catalog`는 기존 공유/자동 퓨징 경로를 유지한다. snapshot_id가 null이면 직렬화와 요청 hash에서 생략해 기존 replay를 보존한다. 전송 실패에는 execution POST를 하지 않으며, execution POST 이후의 통신 오류는 기존 no-blind-resubmit/reconcile/UNKNOWN 계약을 유지한다. 토큰·COM 예약·프로세스 트리·lease·최종 판정 정책은 바뀌지 않는다.

## BSP 플러그인 연동 설계

[RQ-60 설계](BSP_UPGRADE_PLUGIN_INTEGRATION.md)의 `installer_path`와 `tc_patterns`는 제안된 필드이며 구현되지 않았다. 기존 보고 계약을 재사용한다. 일반 GUI Run은 BSP 완료가 아니며 기존 BSP 게이트를 유지한다. 현재 standalone `windows-http`는 거부되고 통합 worker도 BSP이므로 GUI 전용 호스트 연동이 필요하다.
