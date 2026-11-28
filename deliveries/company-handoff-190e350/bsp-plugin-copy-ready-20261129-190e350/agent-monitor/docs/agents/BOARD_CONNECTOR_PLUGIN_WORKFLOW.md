# 회사 BSP 플러그인과 보드 커넥터의 직결 연동 절차

## TC 루트로 실행 요청

회사 호출자가 Linux TC 루트를 지정하면 Windows 보드 커넥터가 그 루트의 `python3`, `dual_board`, `linux` 아래에서 시험을 찾고 실행 순서와 보드를 결정한다. 경로 실행은 `connector-tc-path-v1`을 광고하는 Host와 같은 버전의 참조 CLI를 사용한다.

```sh
python3 plugin.py test run --tc-root /srv/board-tests --no-follow
```

공통 TC 루트를 이미 저장했고 별도 선택 패턴이 없으면 `test run --no-follow`도 같은 경로 실행을 요청한다. 참조 CLI가 공용 파일을 포함한 소스 스냅샷을 동기화하고 경로·스냅샷 식별자·호출 출처를 보낸다. Run 접수에는 기존 멱등 키를 쓴다. 전체 TC 조회나 목록 게시를 선행 호출할 필요가 없다. 필요할 때만 `test list`로 카탈로그를 게시한다. `test prepare`는 같은 경로를 받아 Host가 결정한 계획의 해시를 저장하고 `test send`는 동일 요청을 재전송한다. 경로 지정과 기존 `--pattern` 방식은 각각 사용한다. 회사 명령이 이미 이 참조 CLI에 TC 루트를 전달한다면 추가 선택·ADB·결과 파서 구현은 필요 없다. 회사 전용 래퍼의 실제 전달 여부는 현지 확인 대상이다. [보드 설정과 판정](../gui_test/BOARD_CONNECTOR_EXECUTION.md#tc-루트-실행과-adb)

회사 호출자가 사용할 JSON·종료 코드, 동일 Run 재접수, Host 점유, 프로젝트 밖 export, 모듈 게시, 수동·자동 감시와 납품 검증 명령은 [PORT-017 인수 계약](../porting/PORT-017.md)을 따른다.

회사 플러그인의 명령·훅을 구현하거나 검토할 때 이 문서를 먼저 읽는다. 원본 소스 기준은 `36b7430`이다. 회사에 복사한 패키지에서는 `agent-monitor/docs/agents/BOARD_CONNECTOR_PLUGIN_WORKFLOW.md`에 해당한다. 회사 담당자는 플러그인의 개발 지침과 GUI Test 명령 도움말에서 **채택한 패키지 버전의 이 문서**를 참조한다. 실제 훅·호출 위치는 회사 `COMPANY_MAP.md`, 검증한 버전과 결과는 `APPLIED.md`에 기록한다.

**현재 제공 범위.** Linux 플러그인이 실행 대상을 정해 전달하면 Windows Host가 퓨징·TC·판정을 맡고 기록을 보관한다. Windows Manager는 Host와 SSH 연결을 관리한다. 선택적으로 사용하는 Agent Monitor는 같은 기록을 조회하고 허용된 일시중지·취소를 요청한다. 이 절차는 빌드·검증 이후 승인된 자동 장비 프로파일에 적용한다. 수동 시험과 최초 BSP 계획 확인·최종 사람 검토는 기존 정책을 따른다. [직결 구조와 역할](../design/DIRECT_CONNECTOR_ARCHITECTURE.md) · [장비 시험 정책](../design/AUTOMATIC_FLASH_TEST.md)

**회사 연결 범위.** 아래에서 ‘회사 어댑터’는 회사에 연결할 동작을 뜻한다. 회사 명령 등록, 준비 토큰과 직결 요청의 연결, 응답 유실 복구, 직결 결과의 BSP 반영은 회사 실환경 인수 전이다. 정확한 요청 모델·상태값은 [Host 계약과 실행기](../../backend/gui_test/execution/connector_runs.py), [직결 클라이언트](../../backend/gui_test/standalone/direct_connector_client.py), [공개 명령](../../backend/gui_test/standalone/plugin_commands.py)이 기준이다.

### 실패한 시도의 로그 받기

`test status RUN_ID`에 표시된 `active_analysis.attempt_id`로 아래 명령을 실행한다. 이 조회는 분석 claim이나 TC 재실행을 일으키지 않는다.

```sh
python3 plugin.py test logs RUN_ID --failure-attempt ATTEMPT_ID
```

`logs`는 TC 출력 끝부분, `dmesg`는 대상 보드별 최근 50줄 또는 수집 실패 사유다. `PENDING`이면 같은 ID로 다시 조회하고 `PARTIAL`이면 수집된 내용과 누락 사유를 함께 표시한다. 기존 분석 호출은 Host가 지원할 때 이 묶음을 자동으로 사용한다. 회사 플러그인은 결과를 원래 빌드와 모듈에 연결한다. [응답 계약](../design/DIRECT_CONNECTOR_ARCHITECTURE.md#실패-증거-전달)

## 1. 보드 커넥터와 플러그인 연동

| 단계 | 담당과 절차 | 완료 조건 또는 예외 |
|---|---|---|
| 1-1 환경설정 | 플러그인은 현재 프로젝트의 소스·빌드 경로, 모듈과 시험 선택을 읽는다. Linux 공통 설정에서 TC 루트·허용 폴더·패턴·제한시간·BAT·플래싱 프로파일 이름을 읽는다. Windows는 보드 ID·COM·fastboot 시리얼·프로파일 정의를 관리한다. 최초 Windows 접속에는 도달 가능한 Linux SSH 주소·계정·포트를 설정한다. | 설정 변경은 읽은 버전으로 저장한다. 충돌은 다시 조회해 해결한다. Windows 설정은 실제 적용 응답을 확인한다. 회사 보드 종류만으로 실물 ID를 추정하거나 프로젝트를 열 때마다 전역 BSP 기본값을 바꾸면 다른 작업에 영향을 준다. [설정 매핑](PLUGIN_CONTROL_API.md) · [최초 연결 폴더](../porting/PORT-015.md) |
| 1-2 연결 | 사용자가 Windows에서 연결하면 Manager가 Host와 SSH 역방향 터널을 준비한다. Linux에서 기본 `127.0.0.1:8771`의 식별자·진단·장비 목록을 조회한다. 회사 `bsp gui_test connect`는 즉시 점검용이다. 회사 어댑터는 연결 상태를 계속 보여줄 때 같은 커넥터에 감시 하나를 연결한다. | `connect --watch`의 연결·단절·Runner 교체를 표시한다. 연결 성공 후 대상 보드와 COM, 퓨징 도구 준비 상태를 별도로 검사한다. Runner가 바뀌면 기존 Run과 새 장비를 자동 연결하지 않는다. [감시 및 진단](../porting/PORT-013.md) |
| 1-3 해제 | 플러그인 창 닫기·감시 중지는 관찰 종료로 처리한다. SSH가 끊겨도 Windows가 이미 수락한 Run은 계속된다. Windows의 명시적 연결 해제는 Manager가 처리한다. | 진행·예약·종료 불명 또는 실패 분석 대기 상태에서는 해제가 차단된다. 재접속 시 예상 Runner와 저장한 Run ID를 확인한다. 오프라인 캐시에는 마지막 관측 시점을 표시한다. [연결 해제 구현](../../backend/gui_test/connector/supervisor.py) |
| 1-4 점유·반납 | 회사 GUI Test 서비스가 `batch_reservation_v1`으로 보드 예약과 반납을 관리한다. 회사 CLI의 `scripts/gui_test.py`는 서비스로 HTTP 요청만 보낸다. 따라서 `start` 전후에 플러그인이 별도로 `bsp board lease`를 호출할 필요가 없다. | Windows Host는 접수 시 기존 실행·예약과의 충돌을 검사한다. 플러그인은 서비스가 반환한 상태를 표시한다. 접수 응답이 끊기면 2-3의 절차로 같은 Run을 조회한다. |

모듈 후보 게시와 최초·변경 후 갱신은 [회사 플러그인 연동 요청서](BSP_UPGRADE_PLUGIN_REQUEST.md)를 따른다. Windows에 TC 목록을 표시할 때는 Linux 경로 저장 뒤 카탈로그를 다시 보내고 Host가 표시하는 경로·소스 버전을 대조한다. 공통 설정의 저장 성공만으로 Windows 목록 갱신을 표시하면 이전 목록을 새 것으로 오인할 수 있다.

## 2. 실행

### 2-0. 회사 preview와 start를 같은 실행에 연결

회사에서 확인한 `bsp gui_test start --help`의 옵션 설명은 `--installer REL project-relative installer path (.bat)`이다. `preview`와 `start` 모두 프로젝트 루트 기준 BAT 상대 경로를 받는다. 아래에서 `<rel>`은 해당 상대 디렉터리, `<T>`는 preview에서 받은 준비 토큰이다.

```text
bsp gui_test preview --module ethernet --installer <rel>/install.bat --tc-pattern 'ethernet/*.py'
bsp gui_test start --module ethernet --installer <rel>/install.bat --prepared-token <T>
```

| 입력 | 회사 어댑터가 고정할 값 | 기존 접점과 차이 |
|---|---|---|
| 프로젝트와 BSP 작업 | 프로젝트 식별자·작업 경로·기존 BSP job 및 모듈 ID·이번 빌드 식별 근거 | 새 세션은 기존 job ID로 조회한다. 새 BSP job 시작은 공통 설정을 사용하므로 여러 프로젝트의 설정 저장과 시작 사이에 경로가 바뀌는 경우를 차단해야 한다. |
| 이미지와 보드 | 이번 빌드의 BAT 절대 경로·이미지 묶음 식별 근거, 예상 Runner·실물 보드 ID와 프로파일 리비전 | 옵션명은 양쪽 모두 `--installer`다. 회사 측 상대 경로를 프로젝트 루트에서 해석한 Linux 절대 경로로 직결 클라이언트에 전달한다. 명시 퓨징은 `--flash`를 쓴다. 누락값을 공통 설정에서 읽었어도 BAT와 하위 이미지가 이번 빌드인지 대조한다. 허용 폴더 안의 다른 빌드도 선택될 수 있다. |
| TC와 준비 토큰 | TC 소스 버전·확정된 TC 순서와 의존성·제한시간·실행 방식 | 회사 `--tc-pattern`은 직결 `--pattern`에 대응한다. 직결 `test preview`는 선택값을 보여주고 `test run`은 시작 시 다시 준비한다. 회사 `--prepared-token`을 소비하는 기능은 이 직결 CLI에 없다. 기존 Monitor HTTP 클라이언트의 준비 토큰은 해당 서비스에서 사용한다. [HTTP 클라이언트](../../backend/gui_test/standalone/plugin_client.py) |

**회사 어댑터의 시작 조건.** 준비 토큰을 위 입력과 연결하고 시작 시점의 실제 실행 묶음과 일치할 때만 제출한다. 퓨징 파일·보드·TC·설정이 바뀌면 바뀐 항목을 반환하고 다시 준비한다. 직결 클라이언트가 마지막에 다시 선택하는 값까지 묶어 확인할 접점이 없으면 이 보장은 후속 연결 작업으로 기록한다. TC 단독 실행에는 설치기를 넣지 않는다.

### 2-1. 이미지 퓨징

1. 플러그인이 허용된 Linux 폴더의 BAT 및 그 하위 이미지와 TC 소스를 검증·전송한다. 대상 보드와 활성 프로파일 리비전을 포함한 실행 요청을 Windows Host에 보낸다.
2. Host가 보드를 확인하고 UART에서 `reboot lkshell`을 보낸다. 준비 프롬프트를 받은 뒤 `fast`를 보내고, USB fastboot에서 관측된 대상이 프로파일의 시리얼과 일치할 때 설치 BAT를 실행한다.
3. Host가 BAT 종료 코드·실패 표시를 검사하고 같은 보드 UART에서 **이번 퓨징 이후의 부팅 신호와 로그인 프롬프트**를 확인한다. 대상 불일치·BAT 실패·부팅 확인 실패 시 TC 배정을 중단한다. 플래시 쓰기 중 취소·일시중지는 안전한 경계에서 반영한다. [퓨징 구현 및 상태 전이](../../backend/gui_test/execution/connector_runs.py) · [수동 입력과 설정 우선순위](../porting/PORT-016.md)

### 2-2. TC 실행과 관찰

Host가 수락한 순서로 Single/Dual TC를 실행한다. 각 시도의 실행 ID·TC ID·시도 ID와 종료 상태를 저장한다. 프로세스 종료, 허용 종료 코드, 명확한 `Test Result: PASS` 또는 `Test Result: FAIL` 행을 검사한다. 판정할 수 없는 출력은 오류로 기록한다. Windows 실행 원본은 `executions.db`와 시도별 로그다. 플러그인과 Monitor는 같은 Run을 조회한다. [판정 규칙](../../backend/gui_test/core/results.py)

직결 패키지에서 `plugin.py test status RUN_ID`는 상태 조회, `test logs RUN_ID`는 로그 조회다. `test watch RUN_ID`는 진행을 따라가며 실패 분석 대기에 이르면 설정된 분석·검증에 따라 재시도까지 진행할 수 있다. 조회 전용 화면은 상태와 로그를 읽는다. 재접속 시 저장한 Run ID로 조회하고 로그는 마지막으로 읽은 바이트 위치부터 이어 받는다.

### 2-3. 시작 응답 유실과 새 세션 복구

회사 GUI Test 명령의 응답이 유실되면 **최초 요청을 접수한 GUI Test 서비스**에서 복구한다. 이 저장소의 HTTP 참조 플러그인은 미확인 요청의 키·본문·준비 토큰을 보관하고 같은 서비스에 재전달한다. 동일 요청이면 서비스가 기존 Run의 `id`를 HTTP 202로 다시 반환한다. Run과 후속 예약 상태는 그 서비스에서 조회한다. [서비스 HTTP 계약 시험](../../backend/gui_test/tests/test_plugin_integration_http.py)

**Windows 직결 API를 선택한 호출자**는 첫 전송 전 프로젝트·job·모듈·빌드, Runner·보드, 준비한 요청 본문과 동일 요청을 식별하는 키를 영속 저장한다. Windows `POST /v1/connector-runs`에 이 본문과 `Idempotency-Key` 헤더를 보낸다. 최초 접수(201)와 동일 요청 재접수(200) 모두 응답의 `run_id`를 해당 기록에 연결한다. 복구 조회는 `GET /v1/connector-runs/{run_id}`를 사용한다. 회사 작업과의 연결 정보는 회사 데이터 저장소에서 유지한다. [Windows HTTP 접점](../../backend/gui_test/execution/host.py)

| 상황 | 처리 |
|---|---|
| 시작 요청이 Windows에 도달했는지 불명 | 같은 Runner에 저장한 키와 동일 본문을 재전달한다. Host는 같은 키·요청 해시면 기존 Run을 반환하고 해시가 다르면 409를 반환한다. 요청 원본을 복원할 수 없으면 상태를 미확인으로 남기고 기존 작업을 대조한다. 새 키로 자동 시작하지 않는다. |
| 회사 플러그인을 닫았다 다시 엶 | Runner와 회사 작업에 연결된 Run ID로 상태·미처리 분석·결과 반영 여부를 읽는다. 단순히 가장 최근 Run을 선택하면 다른 프로젝트 결과를 열 수 있다. |
| 직결 CLI를 두 번 호출 | 기본 `test run`은 호출마다 키를 생성한다. Python `start_run(idempotency_key=...)`도 매번 입력을 조립한다. 응답 유실에 대비하려면 PORT-017의 준비 파일을 저장하고 같은 파일로 재전송한다. [요청 생성](../../backend/gui_test/standalone/direct_connector_client.py) · [Host 접수 처리](../../backend/gui_test/execution/connector_runs.py) |

## 3. 결과와 복구

### 3-1. 첫 실패와 재시도

퓨징이나 TC가 처음 실패하면 Host가 해당 Run의 후속 TC 배정을 막고 분석 요청과 근거를 저장한다. 예를 들어 TC 2가 실패하면 TC 1의 PASS와 TC 2의 실패 시도는 보존되고 TC 3은 미실행이다. 플러그인이 시도별 stdout·stderr·UART·설치 로그·연결 진단을 읽는다. 플러그인이 부재하면 분석 요청은 대기한다.

| 판단 | 다음 행동 |
|---|---|
| 원인 조치 미확인 또는 검증기 없음 | 기본 분석 결과는 `HOLD`다. 현재 원인·근거와 대기 사유를 표시한다. 일반 재개 요청으로 분석 대기를 우회할 수 없다. |
| 동일 입력으로 재시도 가능 | 별도 검증기가 조치를 확인하고 Host가 프로세스 종료·장비 준비를 확인한 뒤 `RETRY`를 수락한다. TC 실패라면 같은 Run에서 해당 TC의 새 시도로 이어간다. 같은 원인 재발 또는 자동 재시도 누적 3회 도달 시 추가 자동 재시도를 중단한다. |
| 입력을 변경해 다시 준비 | 검증된 `REPREPARE` 요청으로 자식 Run을 만들고 부모 Run·실패 이력을 연결한다. 플러그인은 자식 ID를 저장하고 결과를 추적한다. |
| 프로세스 종료·장비 상태 불명 | `UNKNOWN`을 표시하고 새 실행·자동 반납을 보류한다. 운영자가 실제 상태를 확인한 뒤 해당 Run에 사유와 함께 중단 확정 또는 실패 분석 이관을 요청한다. SSH가 돌아왔다는 사실만으로 종료를 확정하지 않는다. |

작업자가 멈춘 Run의 `resume`, 실패 조치 후의 `RETRY`, 완료 묶음 전체의 재실행은 이력이 다르다. 회사 어댑터는 사용자가 선택한 동작과 대상 Run ID를 함께 기록한다. [실패 분석과 검증](../../backend/gui_test/standalone/direct_connector_client.py) · [Host 재개·복구 계약](../design/DIRECT_CONNECTOR_ARCHITECTURE.md)

### 3-2. BSP 결과 반영과 종료

회사 어댑터는 직결 Run의 **실행 결과**와 BSP 작업의 **결과 반영 상태**를 별도로 표시한다. Runner·Run ID와 회사 job·모듈·빌드·실물 보드가 일치하는지 확인한다. 필수 TC별 최종 판정과 시도 근거를 매핑하고, 누락·미실행·종료 불명은 미완료로 남긴다. 모든 필수 사례가 통과하면 최종 사람 검토 대상으로 넘긴다. 시험 실패나 결과 전송 실패만으로 Jira에 티켓을 만들지 않는다.

결과 전송 전에 반영 대상을 저장하고 동일 Run과 동일 BSP 대상에 한 번만 반영한다. 수신 응답이 유실되면 기존 접수 기록을 대조하거나 동일 키로 **결과 전송만** 재시도한다. 이미 종료한 장비 시험을 다시 돌릴 필요는 없다. 기존 GUI Test Manager에는 필수 사례 집계와 결과 전송 대기열·수신 확인이 있다. 직결 Host 응답을 이 경로에 매핑하는 회사 어댑터는 별도 인수 대상이다. 장비 종료를 확인한 GUI Test 서비스가 예약을 반납한다. 회사 어댑터는 미전송 결과를 계속 추적한다. [기존 집계·전송](../../backend/gui_test/core/manager.py) · [BSP 수신 처리](../../backend/services/gui_test_host.py)

**현재 자동 반영의 한계.** 기존 BSP 수신 코드에서는 실장비 결과를 제출하면 보드 이미지 검증 어댑터가 없어 `ATTESTATION_REQUIRED`로 차단한다. 자동 반영을 적용할 때는 BSP 수신 측이 신뢰하는 장비 근거를 연결하고, 현재 job의 계획 버전·소스·장비시험 시도·산출물 ID와 SHA-256·필수 사례 매핑을 대조해야 한다. 이 접점의 회사 인수 전에는 플러그인에 ‘TC 통과 / BSP 반영 보류’와 근거를 표시하고 기존 수동 시험 입력 경로를 이용할 수 있다.

## 회사 인수 시나리오

회사 코드에서 확정할 접점은 감시 시작·종료 훅, 빌드 결과·준비 토큰 매핑, 동일 요청 복구 저장 위치, BSP 결과 수신처다. 각 항목은 회사 담당자가 실제 호출 위치·버전과 아래 기대 결과를 기록한다. 원본의 [Host 모의 시험](../../tests/test_direct_connector_unit3.py)과 [플러그인 모의 시험](../../tests/test_direct_connector_unit4.py)을 재사용할 수 있다. 회사 CLI·Windows·실장비 인수는 NOT_RUN이다.

| 검증 상황 | 기대 결과 |
|---|---|
| 커넥터를 나중에 켠 뒤 단절·재연결 | 같은 감시가 연결 상태를 갱신한다. 관찰 창을 닫아도 이미 수락한 Run은 계속된다. |
| A의 preview 후 B 프로젝트를 열거나 BAT·보드·TC를 변경 | A의 start는 변경된 입력을 명시해 재준비를 요청한다. 다른 빌드·보드의 퓨징은 0건이다. |
| 두 프로젝트가 같은 보드에 동시 요청 | GUI Test 서비스의 최초 접수(원본 HTTP 202) 후 준비 단계에서 한 Run만 보드를 점유하고 다른 Run의 상태에는 충돌 사유가 기록된다. 두 플러그인 호출에서 별도 lease 명령은 0회다. |
| Windows 접수 직후 SSH 단절, 새 플러그인 세션에서 복구 | 실행 1건, 동일 Run ID, 진행 중 서비스 예약 유지, 종료 후 서비스 반납 1회, 원래 BSP 작업에 결과 반영 1회다. |
| TC 2 실패 후 같은 원인 재발, 또는 검증된 입력 변경 | TC 3은 대기한다. 동일 원인 재발은 중단하고 입력 변경은 부모와 연결된 자식 Run으로 추적한다. |
| 퓨징 도중 Host 재시작 또는 BSP 결과 접수 응답 유실 | 전자는 종료 불명을 표시해 장비 확인 전 재퓨징을 막는다. 후자는 동일 결과만 재전송하고 보드 실행 건수는 증가하지 않는다. |
| 필수 TC 누락, 보드 이미지 검증 근거 누락 또는 다른 빌드 결과 도착 | 해당 Run과 시도 기록은 조회된다. BSP 작업의 통과 처리는 보류되고 어떤 사례나 근거가 부족한지 표시된다. |
