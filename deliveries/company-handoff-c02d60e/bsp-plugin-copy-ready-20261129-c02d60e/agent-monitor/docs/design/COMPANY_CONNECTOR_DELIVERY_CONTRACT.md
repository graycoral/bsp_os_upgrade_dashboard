# 회사 플러그인용 보드 커넥터 인수 설계

검토 기준은 `018637c6c2ea8751e6bd4ac4094d4babac5aa380`와 2026-11-24 작업 트리다. 이 문서는 설계 세션의 구현 인계안이다. 아래 번호는 회사가 마지막으로 제시한 우선순위다. 명령 철자와 포트 안내는 이미 반영한 작업으로 취급한다. 기존 preview 선택 유지(T-310)와 웹 파일 선택기(T-308)의 작업 트리 변경은 보존한다. 회사 저장소에 적용할 때는 회사의 실제 훅·설정 위치와 적용 이력을 확인한다. [회사 연동 절차](../agents/BOARD_CONNECTOR_PLUGIN_WORKFLOW.md) · [이식 절차](../porting/README.md)

## 필수 1 · 상태를 읽는 프로그램의 계약

대상 명령은 `status --json`, `connect --watch --json`, `test status RUN_ID --json`, `test watch RUN_ID --json`이다. 회사에서는 저장한 Run ID를 넘긴다. 인자 생략 시 기존 CLI의 선택된 Run 조회 규칙을 문서화한다. JSON 모드는 UTF-8 한 줄에 객체 하나를 쓰고 즉시 flush한다. status는 한 줄, watch는 초기 관측과 바뀐 상태를 한 줄씩 보낸다. 설치 진행·오류는 stderr에 둔다. 기존 옵션 없는 명령의 출력·종료 코드를 호환 경로로 둔다. 기존 `test watch`의 실패 분석·재시도 기능은 제품 실행 경로다. 기계용 `test watch --json`은 Run을 관측하며 분석 claim, retry, cancel, reconcile을 호출하지 않는다. [명령 처리](../../backend/gui_test/standalone/plugin_commands.py) · [watch 구현](../../backend/gui_test/standalone/direct_connector_client.py)

| 출력 종류 | 고정 필드 | 상태와 종료 코드 |
|---|---|---|
| 연결 | 정수 `schema_version=1`, `type=connection`, `state`, `runner_id`와 진단 `code`(값이 없으면 null) | `connected` 0, `disconnected` 및 `runner_changed` 3. 연결 watch는 단절·교체를 출력하고 계속 관찰한다. |
| Run | `schema_version=1`, `type=run`, `runner_id`, `run_id`, `state`, Host의 원래 `phase`, `outcome`(미확정 null), 정수 `version` | `queued/flashing/running/pause_requested/cancel_requested/finalizing/passed` 0. `unknown` 3. 분석 래치가 걸린 일시정지는 `hold`, 일반 일시정지는 `paused`로 각각 4. `failed/cancelled/aborted/superseded_by_reprepare`는 5. |
| 명령 종료 | 객체를 완성하기 전 실패한 경우 진단은 stderr로 보낸다. | 명령·전송 오류 1, 문법 오류 2, 사용자가 Ctrl-C로 감시 해제 130. 같은 커넥터 감시가 이미 실행 중인 경우는 5번을 따른다. |

`unknown`은 프로세스 종료나 보드 상태의 미확정을 뜻한다. `hold`는 실패 이후 후속 TC가 차단된 상태를 표시한다. 관측 종료는 장비 명령을 생성하지 않는다. Run 감시는 terminal, hold, paused, unknown에서 마지막 상태에 해당하는 종료 코드를 반환한다. 회사는 현재 버전을 해석하고 추가 필드를 허용한다.

## 필수 2 · Host의 접수·재동기화·점유

`POST /v1/connector-runs`의 전체 요청 스키마를 기존 Pydantic `ConnectorRunRequest`에서 제공하고 공개 스키마와 구현 일치 시험을 둔다. 회사 가이드에는 유효한 `tc_only`·`flash_and_test` 본문 두 가지와 응답 필드·오류 예시를 싣는다. 필수 값은 모드, 보드 연결, 준비된 소스의 ID·리비전, 명령 스냅샷, 순서가 있는 TC 목록이다. 퓨징은 설치 이미지 스냅샷과 활성 프로파일의 리비전을 추가한다. 원본 모델의 제한과 모드별 서버 검사도 명시한다. [요청 모델과 Host 접수](../../backend/gui_test/execution/connector_runs.py) · [HTTP 경로](../../backend/gui_test/execution/host.py)

- 최초 유효 접수는 201. 같은 Host에 `Idempotency-Key`와 같은 JSON 객체를 다시 보내면 실행을 생성하지 않고 같은 ID의 **현재** Run을 200으로 반환한다. 객체 키 순서와 공백은 무관하고 배열 순서와 값은 의미가 있다. 같은 키에 다른 본문은 409 `IDEMPOTENCY_CONFLICT`. 명시된 `run_id` 변경도 포함한다. 삭제한 Run의 키는 410을 유지한다. 최초의 잘못된 요청은 기존 422 계약을 따른다.
- 현 구현은 클라이언트의 `request_hash`를 사용할 수 있다. 새 접수에서는 서버가 최초 JSON 객체에서 계산한 별도 SHA-256을 Run과 같은 트랜잭션에 저장한다. 요청자가 같은 힌트를 보낸 경우도 서버 계산값으로 판정한다. 기존 응답의 `request_hash`를 소비하는 호출자는 계속 동작해야 한다. 새 Run, 재실행, 분석 후 자식 Run 등 모든 생성 경로의 비교 기준을 명시한다.
- 권장 DB 변경은 Windows `executions.db`의 `connector_runs`에 nullable fingerprint 열 하나를 추가하는 것이다. 기존 행의 `request_json`은 타임아웃 등을 계산한 뒤의 steps일 수 있다. 기존 행은 저장된 요청 필드 및 과거 알고리즘으로 입증할 수 있는 본문만 재생하고, 입증 불가 시 409 후 기존 Run ID를 조회한다. 임의의 구형 해시 문자열 일치만으로 재생하지 않는다. 업그레이드·재시작·구 DB 열기 시험을 둔다. 백업은 Host 정지 후 일관된 DB로 만들고 스키마 버전·복원 절차를 PORT에 기록한다.
- Linux에서 최초 POST 전까지 준비한 본문·키·예상 Runner와 프로젝트/빌드 연결을 고정한다. 회사가 준비·전송 단계를 따로 호출하고 저장한 본문으로 재전송할 수 있는 공개 접점을 제공한다. 응답 유실 후에는 현재 설정·시간·인벤토리로 본문을 다시 만들지 않는다. 전송 전 같은 Runner인지 확인하고 수락 후 ID를 보관한다. 소스·설치기 READY 재동기화가 같은 ID를 반환해도 설정·보드·세션을 다시 읽으면 본문이 달라질 수 있다. 일반 `test run`의 독립적인 새 실행과 구분해 사용 방법을 쓴다.
- `9f91123` 기준의 `--project`는 로컬 회사 세션의 상관관계 값이다. 이후 버전의 조회 필터와 서명 검증은 [회사 CLI 후속 계약](../porting/PORT-018.md)을 따른다. Host 모델은 프로젝트별 소유권·권한 분리를 제공하지 않는다. 기본 직결 CLI의 선택·최근 Run은 다른 프로젝트 작업을 포함할 수 있다. 회사가 프로젝트·빌드별로 저장한 Runner 및 Run ID로 조회한다.
- Windows 직결 Host는 활성 Run, UNKNOWN/PAUSED/분석 래치, 기존 실행·예약 등 배타 상태를 검사한다. Host 내 다른 보드도 차단될 수 있다. 단절·watch 종료로 점유를 풀지 않으며 종료 확인 또는 적법한 reconcile로 풀린다. 회사 GUI Test 서비스의 batch 예약·반납, 분석 claim의 TTL/heartbeat, 직접 실행 접수의 Host 배타 조건을 각각 문서화한다. 일반 플러그인이 별도의 보드 lease 명령을 발행할 필요가 없다. [실행·분석 설계](DIRECT_CONNECTOR_ARCHITECTURE.md)

## 필수 3 · 출력 위치와 퓨징 선택

공개 세 명령 `export --output`, `connect export --output`, `settings export --file`은 같은 경로 판정을 사용한다. 회사 플러그인이 작업 경로 밖에서 실행될 수 있으므로 프로젝트 루트를 경로로 전달할 수 있어야 한다. 기존 경로형 `--project`를 보존하고 논리 키와 루트 경로를 구분한다. 경로 미지정 시 호출 위치의 Git 루트, 없으면 현재 디렉터리를 기본으로 삼는다. 설치된 패키지·원본 소스 경계도 보호한다. 절대화·부모 실경로·심볼릭 링크·`..`를 고려하여 루트 자체와 내부 쓰기를 거부하고 디렉터리 생성보다 먼저 검사한다. 파일은 기존 원자적 교체 도구를 사용해 외부 하드링크가 프로젝트 파일을 수정하는 상황도 막는다. stdout으로 내보내는 설정 조회는 기존대로 사용한다. [패키지 출력 경로](../../apps/agent-monitor/plugin_delivery.py) · [CLI 진입점](../../apps/agent-monitor/plugin.py)

직결 CLI에서 `test preview/run`에 `--installer` 또는 `--flash-profile`이 있으면 **정확한** `--flash`가 필요하다. 누락 시 snapshot 준비·전송 및 Run 생성 전에 거부한다. `--flash`는 일회성 명시 확인이며 추가 대화형 질문은 필요 없다. 인자가 없으면 TC만 실행하고, 확인 후에만 저장한 BAT/프로파일을 누락값에 사용한다. 서버의 `execution_mode`·installer 검사를 유지한다. [기존 퓨징 입력](../porting/PORT-016.md)

## 권장 4 · 공식 모듈 목록 게시 명령

플러그인에 `modules list`와 `modules publish --file FILE --expected-version N` 형태의 셸 명령을 제공한다. list는 현재 카탈로그와 버전을 반환한다. publish는 회사 영속 목록을 JSON으로 읽고 명시한 버전으로 한 번 게시한다. 반환값을 stdout에 출력하고 충돌 시 409 원인과 재조회 방법을 표시한다. 입력 JSON 형식과 `group=boot/main` 예시를 동봉한다. 성공한 빈 목록 게시와 원천 조회 실패를 구분한다. Agent Monitor의 실제 연결 주소와 신뢰할 runtime/package identity 및 capability를 확인하고 기존 `BspPluginClient.publish_modules`를 사용한다. 이 명령은 새 대시보드를 기동하거나 8771에 카탈로그를 게시하지 않는다. DB·엔드포인트·선택/고정 모듈의 의미 변경은 필요 없다. [모듈 API](PLUGIN_MODULE_CATALOG.md) · [기존 클라이언트](../../backend/gui_test/standalone/bsp_plugin_client.py)

## 권장 5 · 선택 가능한 활성화 훅과 감시 하나

회사 훅이 활성화될 때 호출할 실행 가능한 예시를 패키지에 싣는다. 자동 시작을 채택한 호스트는 명시적으로 이를 등록하고, 수동 운영에서는 owner가 `connect --watch`를 실행한다. 두 경로는 같은 감시 엔트리·같은 잠금을 사용한다. 회사 호스트가 이미 자식 프로세스 수명을 관리하면 해당 감독 기능으로 감시를 비동기 시작하고 종료 시 자기 소유 handle만 정리한다. 훅 적용만으로 Monitor, 보드 시험, SSH 재시작을 시작하지 않는다.

Linux/macOS에서는 사용자별 동일 커넥터 endpoint를 동일하게 식별하는 OS 파일 잠금을 사용한다. 동일 사용자·endpoint에서 프로젝트·호출 경로가 달라도 잠금 하나가 되어야 한다. `flock(LOCK_EX|LOCK_NB)`를 감시 실행 시작 전에 획득하고 프로세스 수명 동안 유지한다. 잠금 파일의 존재·PID만으로 실행을 단정하지 않는다. 이미 감시 중이면 두 번째 프로세스는 첫 진단 폴링 전에 `already_watching`을 반환하고 성공 종료한다. 죽은 감시의 잠금은 OS가 회수하며, 새 owner가 다시 시작할 수 있다. lock inode 교체·삭제 경쟁을 피하고 전달 중 재실행한 인터프리터에도 동일 범위가 적용되게 한다. 훅의 성공과 커넥터 연결 성공을 구별한다. [기존 관리 잠금](../../apps/agent-monitor/manage.py)

## 권장 6 · Mock 보드 기능과 결과 전달

기존 로컬 Windows Host fixture, 임시 SQLite, 모의 보드 인벤토리와 모의 플래싱 I/O를 재사용한다. 회사가 패키지에서 실행할 수 있도록 fixture와 구체적인 TC 입력, 실행 명령, 필요한 개발 의존성, 시나리오별 기대·실제 결과를 동봉한다. 패키지 엔트리를 이용하는 subprocess 시험과 Host 요청/응답 시험을 함께 둔다. 기존 `tests`는 패키지에 포함된다. `docs/testing/runs`는 기본 수집 경로 밖이므로, 인수 결과 요약은 패키지에 들어가는 가이드에서도 접근 가능해야 한다. [Host fixture](../../tests/test_direct_connector_unit3.py) · [플러그인 fixture](../../tests/test_direct_connector_unit4.py) · [패키징 규칙](../../apps/agent-monitor/delivery.py)

## 선택 7 · 독립 검증용 릴리스 해시

기존 `verify --pristine`과 두 패키지의 manifest를 재사용한다. 이전·새 패키지의 추가/변경/삭제 경로와 전후 SHA-256을 정렬한 표, 소스 커밋·release ID·루트/내부 manifest와 변경표의 SHA-256을 패키지 **밖**에 생성할 수 있게 한다. 수신자는 독립 채널에서 받은 기대 해시를 기준으로 대조하고 변조나 파일 누락 시 실패를 확인한다. 출력 형식은 기존 MANIFEST_DELTA.tsv와 호환한다. 실제 회사 별도 채널에 올리는 담당자·권한은 회사 인수 사항이다. [기존 이식 검증 방식](../porting/PORT-016.md)

## 구현 인계와 판정

| 단계 | 구현 접점 | 완료 판단 |
|---|---|---|
| 1 | Host 요청 비교·schema, 직결 client의 준비·전송 분리 | 최초/응답 유실 후 재생/같은 힌트·다른 본문/병렬 충돌/재시작·기존 DB/unknown 점유를 검사한다. 내부 재실행과 자식 생성 시험을 재실행한다. |
| 2 | plugin 엔트리와 명령 파서, 상태 watch, 세 export | 정상/불명/보류/실패·감시 중단의 stdout·stderr·종료 코드를 검사한다. 경로 우회·기존 파일 보존, 명시 플래그·누락 플래그의 전송 횟수를 확인한다. |
| 3 | 모듈 CLI, 감시 잠금과 활성화 예시 | 실제 CLI ↔ 로컬 full Monitor로 게시·충돌·빈 목록을 검사한다. 두 프로세스 동시 기동, 수동→훅, 훅→수동, 비정상 종료 후 재획득을 검증한다. |
| 4 | Mock 입력·실행 결과, 해시 비교, 회사용 PORT·패키지 안내 | 새로 내보낸 패키지에서 문서·fixture·엔트리를 검증하고, 변경·추가·삭제·변조를 각각 대조한다. 테스트 ID, 코드/시험 기준, 결과와 남은 실환경 인수를 남긴다. |

기존 RQ-74~83과 T-288~310에 영향을 주는 회귀를 선별하고, 구현에서 회사의 새 인수 조건에 별도 RQ/T를 배정한다. Linux 측 CLI와 Windows 측 Host를 같은 전달 단위로 이식한다. DB 변경은 Host에 국한한다. GitHub 게시, 회사 훅 설치, 실제 Windows/COM/fastboot, 회사 릴리스 채널 게시는 이번 로컬 모의 검증 경계 밖이다. 설계 시점의 구현·독립 코드 리뷰·실장비 인수는 각각 미실행 상태다.
