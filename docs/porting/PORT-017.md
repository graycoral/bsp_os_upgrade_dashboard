# PORT-017 · 회사 플러그인의 CLI·직결 Run 인수 계약

회사 플러그인 담당자는 이 문서를 복사형 패키지의 `agent-monitor/docs/porting/PORT-017.md`에서 읽는다. 선행 기능은 [플러그인 폴더 전달](PORT-011.md), [후보 모듈 API](PORT-012.md), [Windows 직결 Host](PORT-013.md), [퓨징 설정](PORT-016.md)이다. 설계·우선순위는 [회사 인수 설계](../design/COMPANY_CONNECTOR_DELIVERY_CONTRACT.md)에 있다. 원본 비교 커밋은 `018637c6c2ea8751e6bd4ac4094d4babac5aa380`이다. 구현 커밋은 `9f911235d98df0120593d3028a27fcfdee5cead3`이다. 회사 적용 버전과 인수 결과는 현지 APPLIED.md에 기록한다.

## 조회 명령과 종료 코드

패키지 루트에서 다음 명령을 실행한다. `RUN_ID`는 회사의 프로젝트·빌드에 연결해 저장한 직결 Run ID다. ID를 생략하면 state 디렉터리의 `selected-run.txt`, Host의 활성 Run, 가장 최근 Run 순서로 조회한다. 실행 이력이 없으면 `NOT_FOUND`와 종료 코드 1을 반환한다. 여러 프로젝트가 한 Host를 쓰는 환경에서는 ID를 지정한다.

```sh
python3 plugin.py status --json
python3 plugin.py connect --watch --json
python3 plugin.py test status "$RUN_ID" --json
python3 plugin.py test watch "$RUN_ID" --json
```

stdout은 UTF-8 JSON 한 줄에 관측 한 건이다. status는 한 번 출력한다. watch는 초기 관측과 변화를 출력할 때마다 flush한다. 파서는 추가 필드를 허용하고 `schema_version`을 확인한다. 오류·설치 진단은 stderr에서 읽는다. `test watch --json`은 조회용이다. 기존 `test watch`를 호출하면 실패 분석과 후속 재시도가 진행될 수 있다.

```json
{"schema_version":1,"type":"connection","state":"connected","runner_id":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","code":"CONNECTED"}
```

```json
{"schema_version":1,"type":"run","runner_id":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","run_id":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb","state":"hold","phase":"PAUSED","outcome":null,"version":4}
```

| 종료 코드 | 회사 호출자가 처리할 값 |
|---|---|
| 0 | 연결 가능, 동일 endpoint의 기존 감시 확인(`already_watching`), 진행 중 또는 통과. Run의 `queued`, `flashing`, `running`, `pause_requested`, `cancel_requested`, `finalizing`, `passed`를 구분한다. |
| 1 | 명령 처리·통신 실패. stderr의 원인을 기록한다. |
| 2 | 명령 구문 오류. 호출 인자를 수정한다. |
| 3 | 연결의 `disconnected` 또는 `runner_changed`, Run의 `unknown`. 연결 watch는 이 상태를 출력한 뒤에도 관찰을 계속한다. |
| 4 | `hold`는 실패 분석으로 후속 실행이 막힌 상태, `paused`는 일반 일시정지다. |
| 5 | 완료 결과 `failed`, `cancelled`, `aborted`, `superseded_by_reprepare`. |
| 130 | 사용자가 Ctrl-C로 감시를 끝냈다. Windows가 이미 수락한 실행의 결과는 Run ID로 다시 조회한다. |

## Windows Host 접수와 복구

직접 HTTP를 호출할 때는 Host identity의 `connector-run-replay-v1` capability를 확인하고 최초 Runner ID를 `X-Expected-Runner-ID` 헤더로 고정한다. Runner가 바뀌면 Host가 409 `RUNNER_CHANGED`를 반환한다. Linux의 SSH 역방향 터널을 통해 `POST /v1/connector-runs`로 JSON을 보낸다. 헤더는 `Content-Type: application/json`, `Idempotency-Key: <작업별 고정 키>`다. 키 길이는 1~180자다. 아래 예시의 Runner·보드·소스·이미지·프로파일 리비전·TC 값은 모의 값이다. 실제 제출에서는 같은 Host에 준비한 값으로 교체한다.

### TC만 실행하는 요청

```json
{
  "execution_mode": "tc_only",
  "connection": {"a": {"host": "WINPC", "board_id": "B1", "com": "COM3"}},
  "source_snapshot_id": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "source_revision": "source-example",
  "command_snapshot": {
    "name": "default",
    "revision": "cmd-example",
    "template": {
      "single": ["python", "{tc_path}", "--com", "{com_a}"],
      "dual": ["python", "{tc_path}", "--a", "{com_a}", "--b", "{com_b}"]
    }
  },
  "tests": [{"step_index": 0, "tc_id": "t1.py", "path": "t1.py", "kind": "Single"}],
  "origin": {"client": "plugin", "session_id": "company-bsp"}
}
```

### 퓨징 후 TC를 실행하는 요청

```json
{
  "execution_mode": "flash_and_test",
  "connection": {"a": {"host": "WINPC", "board_id": "B1", "com": "COM3"}},
  "source_snapshot_id": "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
  "source_revision": "source-example",
  "command_snapshot": {
    "name": "default",
    "revision": "cmd-example",
    "template": {
      "single": ["python", "{tc_path}", "--com", "{com_a}"],
      "dual": ["python", "{tc_path}", "--a", "{com_a}", "--b", "{com_b}"]
    }
  },
  "installer": {
    "installer_snapshot_id": "bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
    "flash_profile": "board-b1",
    "flash_profile_revision": "cccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccccc"
  },
  "tests": [{"step_index": 0, "tc_id": "t1.py", "path": "t1.py", "kind": "Single", "effective_timeout_s": 120}],
  "origin": {"client": "plugin", "session_id": "company-bsp"}
}
```

TC 목록은 1~2000개이며 순번은 0부터 이어진다. Host는 소스 리비전·TC 경로·종류·의존 순서, 실행 환경과 보드 매핑을 확인한다. Dual TC에는 동일 Host의 서로 다른 두 보드가 필요하다. 직결 요청을 준비하기 전에 회사 Windows용 명령 프로파일을 등록한다. 예시 본문의 `command_snapshot.template` 객체를 JSON 파일로 저장하고 `python3 plugin.py settings profiles save --kind commands --name default --file "$OUTSIDE/commands.json"`을 호출한다. 프로파일이 비면 데모용 `mock-tc`로 조립되어 Host가 `COMMAND_NOT_ALLOWED`로 거부할 수 있다. 퓨징은 준비된 설치 이미지와 활성 프로파일의 리비전도 확인한다.

| 응답 | 호출자의 후속 처리 |
|---|---|
| 201 | 최초 수락. 응답의 `runner_id`, `run_id`, `state`, `version`을 기록한다. 수락 직후 상태는 `QUEUED`일 수 있다. |
| 200 | 같은 키와 같은 JSON 객체를 다시 받았다. 동일 ID의 **현재** Run을 반환한다. 배열 순서와 값은 보존하고 JSON 객체 키 순서·공백은 자유롭다. |
| 409 `IDEMPOTENCY_CONFLICT` | 키에 연결된 본문이 다르거나 이전 기록과의 일치를 입증할 수 없다. 저장한 원요청과 기존 Run을 확인한다. |
| 409 `ACTIVE_RUN_EXISTS` / `RESERVATION_CONFLICT` | 기존 실행·예약을 확인한다. 활성 직결 Run이 있으면 응답의 `active_run_id`로 조회할 수 있다. |
| 410 `RUN_DELETED` | 영구 삭제된 Run의 키다. |
| 422 | 최초 요청에 키·필수 입력이 없거나 형식·모드·장비·스냅샷 검증이 실패했다. 응답의 `code`, `message`를 확인한다. |

존재하는 키의 본문 불일치 응답 예시는 `{"code":"IDEMPOTENCY_CONFLICT","message":"Cannot match the accepted request. Query the existing Run ID.","run_id":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"}`다. 회사는 분기 시 `code`를 읽는다. 상태 조회는 `GET /v1/connector-runs/{run_id}`다. 같은 키를 사용하는 곳은 최초 요청을 수락했던 Windows Host다. 회사 GUI Test 서비스의 HTTP 202 재접수 절차는 [서비스 연동 절차](../agents/BOARD_CONNECTOR_PLUGIN_WORKFLOW.md)에 있다.

프로젝트 키는 Linux 플러그인의 작업 문맥에 쓰인다. 직결 Host에는 프로젝트별 소유권·접근 분리 필드가 없다. 회사 저장소에 **프로젝트·빌드·Runner·키·최초 본문**을 먼저 기록하고, 수락하면 Run ID를 연결한다. 같은 파일을 재동기화해도 현재 보드·명령·제한시간·세션이 달라졌을 수 있으므로 응답 유실 때는 저장한 본문을 그대로 보낸다.

### 누가 보드를 점유하는가

| 소유자 | 점유와 반납 |
|---|---|
| 직결 Windows Host | 승인된 활성 Run과 미해결 장비 상태는 Host 전체의 신규 Run을 막는다. 다른 보드를 지정해도 충돌할 수 있다. TC·퓨징 진행, 일시정지, 분석 대기, `UNKNOWN`에서 점유가 유지된다. 종료 확인 후 해소하며 `UNKNOWN`이면 장비 확인과 reconcile을 거친다. SSH 단절과 watch 종료는 반납 조건에 포함되지 않는다. |
| GUI Test 서비스의 batch 예약 | 기존 `batch_reservation_v1` 서비스가 예약 토큰·epoch·종료 확인을 관리한다. 서비스 경로를 쓰는 플러그인은 결과를 조회하며 별도의 회사 보드 lease 명령을 발행할 필요가 없다. |
| 실패 분석 담당자 | 분석 claim의 TTL은 기본 120초이며 heartbeat로 연장한다. 만료되면 분석을 다시 맡을 수 있다. 이 시점에도 장비 Run의 분석 래치는 유지될 수 있다. |


### 응답 유실 후 동일 요청 전송

공개 요청 스키마는 [connector-run-request-v1](../../contracts/connector-run-request-v1.schema.json), 패키지 예시는 [tc_only](../../examples/connector-runs/tc_only.json)와 [flash_and_test](../../examples/connector-runs/flash_and_test.json)다. 회사 어댑터가 실행 가능한 파일을 준비한 뒤 장비 요청을 명시적으로 보내는 예다. `OUTSIDE`는 프로젝트·패키지 밖에 있는 회사 전용 상태 디렉터리다. 운영자는 각 빌드에 고유한 준비 파일을 사용한다.

```sh
python3 plugin.py --project "$PROJECT_KEY" --project-root "$PROJECT_ROOT" test prepare \
  --build "$BUILD_ID" --file "$OUTSIDE/request.json" --tc-root "$TC_ROOT"
python3 plugin.py --project "$PROJECT_KEY" --project-root "$PROJECT_ROOT" test send \
  --file "$OUTSIDE/request.json"
```

응답 수신 여부가 불명확하면 같은 Runner에 연결한 후 두 번째 명령만 다시 실행한다. 일반 `test run`은 매번 새 의도를 생성한다. 퓨징 빌드의 경우 준비 단계에서 `--flash`와 이번 빌드에 해당하는 설치 BAT·프로파일을 선택하고, 제출·재전송에도 `test send --file FILE --flash`를 쓴다. TC 전용 요청은 두 단계 모두 `--flash`를 생략한다.

## 출력 경로와 명시적 퓨징

- `connect export --output`, `settings export --file`, `export --output`의 출력 위치는 회사 프로젝트와 패키지 소스 밖에 둔다. 작업 디렉터리와 프로젝트가 다르면 전역 `--project-root PATH`를 지정한다. `--project KEY`에는 논리 식별자를 사용할 수 있다. stdout으로 받는 `settings export`도 가능하다.
- `test preview` 및 `test run`의 기본 모드는 TC 전용이다. `--installer`나 `--flash-profile`을 지정하면 정확한 `--flash`도 전달해야 한다. `--flash`가 있는 경우에만 누락한 BAT·프로파일을 저장값에서 보완한다. 회사는 저장된 BAT의 빌드 식별자와 대상 보드를 확인한다. 공개 명령의 문서화된 이전 설치기 단독 호출자는 함께 갱신한다.

## 모듈 후보 목록 게시

대상은 `plugin-module-catalog-v1`을 제공하는 실행 중인 **전체 Agent Monitor**다. 회사의 영속 모듈 조회에 성공한 후 JSON 배열을 준비한다.

```json
[{"stable_key":"bsp/kernel","name":"Kernel","group":"boot","target_paths":["kernel"]}]
```

```sh
python3 plugin.py modules list
python3 plugin.py modules publish --file "$OUTSIDE/modules.json" --expected-version "$VERSION"
```

`VERSION`은 첫 명령의 `version`이다. 성공 시 `version`과 `modules`가 돌아온다. 409이면 현재 목록을 다시 읽고 회사 변경을 대조한다. 성공한 원천 조회가 0건일 때만 빈 배열을 게시한다. 기존 선택 모듈과 이미 시작한 job의 목록은 유지된다. 이 목록은 Monitor 인스턴스의 공유 후보이므로 여러 프로젝트의 게시 시점과 범위는 회사에서 정한다. 관리형 Monitor에는 같은 `--home`을 쓴다. 비관리형 Monitor는 전역 `--monitor-port PORT`와 modules 명령의 `--runtime-id ID --package-version VERSION`으로 신뢰할 인스턴스를 지정한다.

## 수동 owner와 선택적 시작 훅

현재 회사 운영에서는 owner가 `python3 plugin.py connect --watch --json`을 실행하면 된다. 자동 시작을 선택한 설치에서는 [활성화 훅 예시](../../examples/activate-connector-watch.sh)를 사용해 같은 감시 진입점을 호출한다. 회사 등록 시에는 플러그인 경로와 연결 포트를 명시하고 감시 자식 프로세스의 수명을 해당 호스트에서 관리한다. 동일 사용자·endpoint에 감시가 있으면 후발 호출은 `state=already_watching`, `code=ALREADY_WATCHING`과 종료 코드 0을 반환한다. 훅을 호출했다는 사실과 실제 커넥터가 연결됐다는 관측은 별도로 기록한다.

## 릴리스 변경 파일과 검증값

검증 명령은 신뢰할 수 있는 PORT-017 이상 버전의 설치본에서 실행한다. 두 패키지의 검증 자료를 로컬에서 생성한다. `EVIDENCE_DIR`는 두 패키지와 프로젝트 밖의 새 디렉터리다. 이전 릴리스의 폴더를 보존한다.

```sh
python3 plugin.py release-evidence "$PRIOR_PACKAGE" "$CURRENT_PACKAGE" --output "$EVIDENCE_DIR"
python3 plugin.py verify-evidence "$PRIOR_PACKAGE" "$CURRENT_PACKAGE" "$EVIDENCE_DIR" --sha256 "$EXPECTED"
```

생성되는 파일은 `MANIFEST_DELTA.tsv`와 `RELEASE_EVIDENCE.json`이다. 배포 담당자가 출력한 후자 파일의 기준 SHA-256을 회사가 신뢰하는 별도 채널에 기록하면, 수신자가 그 값을 `EXPECTED`로 사용해 release와 파일별 전후 해시를 대조할 수 있다. 배포물과 함께 받은 해시만으로는 제공자를 독립적으로 확인할 수 없다.

## 패키지에서 Mock 보드 시험 실행

Linux 또는 macOS, Python 3.11 이상, Git, 사용 가능한 로컬 loopback 포트가 필요하다. 검증용 가상환경은 패키지 밖에 만들고 `agent-monitor/requirements.lock`의 개발 의존성을 설치한다. 패키지 루트에서 실행한다.

```sh
cd agent-monitor
PYTHONDONTWRITEBYTECODE=1 python3 -B -m pytest -q -p no:cacheprovider \
  tests/test_connector_run_replay.py tests/test_connector_observation.py tests/test_company_connector_delivery.py
python3 -IB ../plugin.py verify .. --pristine
```

실행 입력은 [모의 TC](../../examples/connector-runs/mock_smoke.py), [모듈 후보 샘플](../../examples/connector-runs/modules.json), 이 문서의 두 Run 본문이다. 시험은 임시 Windows Host DB와 loopback HTTP 서버를 만들고, 모의 TC만 실행한다. 기계용 watch와 훅은 별도 프로세스로 호출해 출력·종료 및 잠금 해제를 검사한다. 회사 프로젝트, 보드, SSH 계정은 필요하지 않다.

### 원본 Mock 인수 결과

| 시나리오 | 로컬 실행에서 확인한 결과 |
|---|---|
| JSON status/watch·owner 수명 | 정상·단절·교체·재연결, Run의 hold/unknown/완료, Ctrl-C를 판별했다. 수동/훅 동시 기동에서 감시는 하나였고 기존 owner 종료 후 새 owner가 획득했다. |
| Host 접수·점유·복구 | 동시 요청에서 실행 1건, 동일 키·본문 재생 200, 변경 본문 409, 구형 DB 복구, Runner 교체 거부와 UNKNOWN 점유를 확인했다. |
| 명시적 퓨징·export | 플래그 누락과 모드 불일치 때 Run을 생성하지 않았다. 프로젝트 내부·경로 별칭은 거부했고 외부 설정을 쓸 때 하드링크로 연결된 원본 파일이 보존됐다. |
| 모듈·배포 증거 | full Monitor에 목록 게시·409 충돌·빈 목록 게시, 추가/변경/삭제 파일과 불일치 해시 거부를 확인했다. |

패키지 안에서 위 명령으로 신규 시험 33건이 통과했다(Host 7, 관측 19, 패키지 7). 시험 전후 패키지 파일 검증도 통과했다. 회사 Linux 훅, 실장비 플래싱·TC, 독립 사내 릴리스 채널은 회사 인수 항목이다.

## 적용과 복원

Linux 패키지 진입점과 Windows Host를 같은 PORT 기준으로 준비한다. 기존 실행의 ID와 상태를 기록하고 Host 정지 후 `executions.db` 및 WAL의 일관된 백업을 확보한다. Host는 스키마 3을 열 때 기존 Run 테이블에 nullable `body_fingerprint` 열을 추가한다. 구형 Run은 저장된 데이터로 요청 일치를 확인할 수 있을 때만 재생하고, 불확실하면 409에 동봉된 기존 Run ID로 조회한다. 기존 home/runtime과 SSH 설정을 유지한다. 업데이트 후 새 프로세스에서 기존 Run 조회, 수동 감시와 중복 감시 판정, 동일 준비 파일 재접수를 검증한다. 패키지를 되돌려야 하면 먼저 작업을 정지하고 이전 소스·설정과 그 버전에 맞는 DB를 복구한다. 변경 이후 접수한 실행은 별도 보존하고 장비 상태와 대조한다. 진행 중인 보드 작업에 과거 DB를 덮어쓰면 재실행 위험이 있다.


### 이식 파일 지도

| 위치 | 적용 단위 |
|---|---|
| `apps/agent-monitor/{plugin,plugin_delivery}.py` | Linux CLI, 프로젝트 경로 전달, 모듈 명령·준비 파일·내보내기·검증, 패키지 README와 증거 생성 |
| `backend/gui_test/standalone/{plugin_commands,direct_connector_client,connector_observation,module_commands}.py`, `backend/gui_test/core/plugin_paths.py` | 실행·관측, 감독 프로세스 잠금, 모듈 API, 출력 경로 검사와 원자적 저장 |
| `backend/gui_test/execution/{host,connector_runs}.py` | Windows Host 식별·capability, 스키마 3 이전, 원본문 비교 및 재생 |
| `contracts/connector-run-request-v1.schema.json`, `examples/connector-runs/`, `examples/activate-connector-watch.sh` | 공개 스키마·입력, 모의 TC, 선택적 시작 훅 |
| `tests/test_{connector_run_replay,connector_observation,company_connector_delivery}.py`, `tests/test_direct_connector_unit{3,4}.py`, `tests/test_plugin_delivery.py` | 새 인수 시험, 기존 플래싱·자식 Run·패키지 재내보내기 회귀 |
