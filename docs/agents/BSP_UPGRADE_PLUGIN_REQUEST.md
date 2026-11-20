# 회사 bsp-upgrade 플러그인 연동 요청서

## 2026-11-20 · 직결 보드 커넥터 · 대시보드 후속 (`PORT-013` / `PORT-014`)

고정 코드·시험 커밋: [PORT-013](../porting/PORT-013.md) `b71653b` (직결 본체) → [PORT-014](../porting/PORT-014.md) `ed6a6f0`~`d83cc11` (`TestPage` `tc_root` 폴백/`전체 TC 보기`/자율 실행 표시, 작업 삭제/재실행, 단일 진행률 박스, 회사 `8765` 격리). 상세 파일·보존 정책·조정 포인트는 각 PORT를 따른다.

- **회사 대시보드 이식 시 필수 확인:**
  - `apps/agent-monitor/recovery.py`의 `RESET_TABLES['connector-registry.db']`에 `'direct_cache'`와 `'shared-settings.db'`를 반드시 함께 반영해야 `reset`/`doctor`가 `RESET_BLOCKED`로 실패하지 않는다.
  - `apps/web`·`packages/gui-test-ui` React 변경분 반영을 위해 Node 22+ 환경에서 `bash scripts/build-ui.sh`를 실행해야 한다.
- **회사 플러그인 필수 연결:**
  - `bsp list --available` 결과를 `BspPluginClient.publish_modules()`(`PUT /api/v1/config/modules`)로 게시해야 대시보드 환경설정의 모듈 콤보박스가 채워진다.
  - 직결 자율 실행은 `POST /v1/connector-runs`·`POST /v1/connector-runs/{id}/rerun`을 사용하며 새 세션에서 `test watch`/`test analyze`로 이어받을 수 있다.

## 2026-11-18 · TC 목록이 포함된 새 전달물 사용

[PORT-011 최신 TC 목록 전달](../porting/PORT-011.md#2026-11-18--tc-목록-포함-전달-후속)을 적용한다. 같은 source의 Linux API/Manager·공유 view·ZIP을 사용하고 test list GET은 BAT 없이 조회한다. 기존 active service/Manager를 단순 start로 재사용하면 구버전 코드가 유지되므로 PORT의 안전 release 갱신 절차와 실제 running 소스를 확인한다. 공통 설정/Run과 다른 timeout/Mock 작업은 보존한다.

최신 TC 목록 코드·시험 고정 커밋: `665eeb164dbc756426f17323e2cd5d2c6846455f`. 실제 전달 hash와 안전 갱신은 위 최신 절을 따른다.

2026-11-18 RQ-74 고정 코드·시험: `3af0f09f24a5e3a754ec7bd645aca8c4e9f3b6ac`. 전달·설정 공유·회사 Git 이동 절차는 [PORT-011](../porting/PORT-011.md)을 따른다.

## 2026-11-18 · 보드 커넥터를 플러그인 Git으로 이동

[PORT-011 최신 구현](../porting/PORT-011.md#2026-11-18--플러그인-git-소유의-독립-구현과-설정-파일-공유)을 우선 적용한다. 원본의 plugin.py/PluginSession/SettingsFileBridge와 동봉 GUI 소스를 그대로 복사하고 회사에서는 등록·표시·hook만 연결한다. 회사 dashboard Git의 중복 소스는 소비자 연결/검증 후 제거하며 공통 runtime/공유 설정 파일·DB는 저장소 밖에 유지한다. UI 표시 삭제 지시와 혼동하지 않는다. 실제 회사 삭제·이식/장비 인수는 NOT_RUN이다.

- **보드 커넥터와 플러그인 연결 필수:** 플러그인(`plugin.py` / `PluginSession` 및 후속 [PORT-013](../porting/PORT-013.md) 직결 계약)과 보드 커넥터는 반드시 연결되어야 한다(`connect --watch`로 `127.0.0.1:8771` 주기 감시 및 `CONNECTED`/`DISCONNECTED`/`RUNNER_CHANGED` 알림, 플러그인 종료 시 실행 취소 없이 안전 분리, 최초 연결 JSON/bootstrap 전달).
- **보드 커넥터 반입·가져가기 경로(폴더 기준):** 보드 커넥터(Windows)는 플러그인 측 전달 패키지(또는 플러그인 Git에 반입된 vendor 경로) 내 **`<플러그인-전달-또는-vendor-루트>/agent-monitor/` 폴더 전체**(`board-connector.bat`·`board-connector.cmd`·`scripts/`·`backend/`·`apps/`·`packages/` 포함)를 그대로 가져가서 그 루트의 `board-connector.bat` / `board-connector.cmd`를 실행해야 한다(`board-connector.bat`/`.cmd` 단독 복사 불가). 별도 ZIP 아카이브를 생성하지 않고 폴더를 그대로 복사한다.
- **회사 대시보드 스크립트 정렬 (`run.sh` 등):** 회사 대시보드의 실행·관리 스크립트(`run.sh`, `scripts/*`, `apps/agent-monitor/manage.py`, `board-connector.bat`, `board-connector.cmd`)는 이 저장소 기준으로 맞춘다. 특히 `run.sh`는 체크아웃별 `--home`(기본 `${BSP_HOME:-$root/.monitor-home}`)과 `--runtime`(기본 `${BSP_RUNTIME:-$root/.runtime}`)을 함께 전달해, 같은 Linux 서버에서 원본 대시보드와 파생 회사 대시보드를 동시에 실행해도 `stop`/`restart`가 서로의 `service.json`·`runtime-location.json`과 충돌하지 않도록 한다(동시 실행 시 두 번째 대시보드는 `BSP_PORT`로 포트만 분리).
- **플러그인 모듈 후보 목록 게시 필수 (`D-82` / [PORT-012](../porting/PORT-012.md)):** 대시보드 환경설정의 `모듈 추가 → 플러그인 모듈 선택`이 동작하려면 플러그인에 회사 영속 모듈(`bsp list --available` 결과 등)을 `BspPluginClient.publish_modules()`로 `/api/v1/config/modules`에 게시하는 기능을 반드시 추가해야 한다(세션·모델 응답으로 자동 대체 금지; 미게시 시 `version: 0, modules: []`로 드롭다운 비활성화).

Windows 클릭 실행 후속: 전체 소스에 루트 `board-connector.bat`와 `board-connector.cmd`를 함께 제공한다. BAT는 AutoRun을 끈 CMD에서 기존 실행기를 호출하며 설치 코드를 복제하지 않는다. `board-connector.bat --server-port 8765`로 서버 포트를 저장하고 이후 더블클릭은 저장값을 사용한다(최초8766). [실행·포트 안내](../gui_test/TEST_BOARD_CONNECTOR_GUI.md#windows-더블클릭서버-포트). Windows CI의 실제 BAT/CMD+stub 계약 T-279는 PASS이며 회사 클릭·GUI 인수는 별도다.

## 2026-11-17 · 사용자 명령·CONNECT 알림·설정 상호 갱신

플러그인 담당자는 [PORT-011](../porting/PORT-011.md)의 리뷰 반영 권고 명령과 회사 접점을 먼저 확인한다. 커넥터가 뒤늦게 연결돼도 상태를 갱신해 연결 준비 완료를 알리고, 공통 설정의 양방향 CAS·Windows 실제 적용 receipt·미저장 초안을 유지한다. 이는 설계 전달이며 slash 명령/감시 adapter 구현·회사 인수 완료가 아니다. [검토·문서 검사](../testing/runs/20261117-plugin-command-porting.md).

## 2026-11-17 · 새 작업 구현 기본값 적용

코드·시험 기준은 `b7735ac8f84fb04c537311c8eaed42c531f5a4e7`다.

플러그인은 `backend/settings.py::prepare_job_profile`의 기본값 적용을 포함한다. 과거 형식의 설정으로 직접 Engine.create를 호출해도 새 job은 미지정 구현 도구=Claude, 미지정/빈 Claude 모델=Sonnet으로 고정되어야 한다. 명시 선택은 보존한다. 회사 자체 생성 함수도 같은 정책을 새 job 저장 전에 적용한다.

Agent Monitor는 동일한 backend를 API·Worker에 적용하고 기존 runtime을 유지하여 재시작한다. 화면의 실제 attempt.tool을 다른 이름으로 바꾸지 않는다. 기존 작업·이력·멱등 요청은 보존한다. 보드 커넥터 수정은 없다. [고정 코드·파일·복원](../porting/PORT-010.md#새-작업-직접-생성-기본값-보완), [시험·회사 미확인 범위](../testing/runs/20261117-new-job-tool-default.md)를 전달한다.

## 2026-11-17 · 커넥터 실행 시 서버 포트 지정

코드·시험 기준은 `8849a281cb16618b3ae2cb78fbe209f4687af360`다.

Windows는 `board-connector.cmd --server-port 8765`로 실행한다. 생략하면 기존 저장값을 유지하고 처음에만 `8766`을 사용한다. 설정 화면과 같은 `windows-runner.json`에 저장하며 SSH/Windows 로컬 포트는 변경하지 않는다.

플러그인 담당자는 기존 연결 JSON에 실제 Agent Monitor 포트를 계속 전달하고 복사형 커넥터에 이번 launcher·Manager 변경을 포함한다. 연결 JSON과 CLI 옵션이 함께 있으면 CLI 값이 우선하며 서비스 identity는 유지한다. Agent Monitor 담당자는 서버 포트 변경을 Windows 담당자에게 전달한다. 서버가 바뀐 포트를 커넥터가 자동 탐지하는 기능은 아니다. Linux HTTP API 변경·UI 재빌드는 필요 없다.

Windows 담당자는 연결 종료 후 새 옵션으로 실행·재연결한다. 기존 Manager가 옵션을 지원하지 않으면 작업 종료 후 같은 버전으로 다시 시작한다. [파일·복원·검증](../porting/PORT-009.md#2026-11-17--서버-포트-실행-옵션), [사용 명령](../gui_test/TEST_BOARD_CONNECTOR_GUI.md#서버-포트-지정).


## 2026-11-17 · 보드 COM 멀티플렉서 자동 적용

코드·시험 기준은 `59af913972b4898f9da37f4174816a3869be895e`다.

플러그인 담당자는 복사형 패키지에 [PORT-009의 자동 적용 변경](../porting/PORT-009.md#2026-11-17--자동-멀티플렉서)을 포함한다. TC별 COM 인자와 기존 serial 호출을 그대로 전달한다. 사용자가 RX COM이나 serial_proxy import를 설정하도록 요구하지 않는다. Windows desired의 native 값은 proxy로 정규화하며 실제 적용 receipt를 확인한다.

Agent Monitor 담당자는 공통 설정 검증과 ConnectorMirror를 함께 갱신하고 화면을 재빌드한다. 통신 방식/RX 입력을 제거하고 실제 Host의 준비 상태를 표시한다. Windows 담당자는 커넥터 소스를 갱신한 뒤 안전하게 종료·다시 연결한다. 기존 프로파일은 자동 전환되며 실행·예약·UNKNOWN이 남으면 보류한다. TC Python의 기존 pySerial은 필요하다.

설치·사용은 [커넥터 가이드](../gui_test/TEST_BOARD_CONNECTOR_GUI.md#최초-설정), 적용 파일·복원은 [PORT-009](../porting/PORT-009.md), 검증·제약은 [실행 기록](../testing/runs/20261117-automatic-serial.md)을 따른다. 실제 Windows 11/Python 3.13·회사 공통 모듈·UART·PuTTY 인수는 NOT_RUN이다.

2026-11-17 추가 요청: Linux 대시보드 `bash run.sh force-stop`, Windows `board-connector.cmd --force-stop`을 각각 명시적 비상 조작으로 제공한다. 정상 stop/disconnect나 창 닫기에 자동 연결하지 않는다. 같은 버전의 소유권 receipt·공통 종료 모듈·pending/start barrier를 함께 적용한다. [명령·결과·복구](../gui_test/FORCE_STOP.md), [PORT-007](../porting/PORT-007.md), [PORT-009](../porting/PORT-009.md), [검증·미실행 범위](../testing/runs/20261117-connector-cleanup.md)를 따른다.


## 2026-11-17 · 보드 커넥터 명칭·설치·스크립트 정리

이번 코드·시험 고정 커밋은 `b6f1c30fb0ba8a3a13d1b16544fd8c0c0254a0f7`다. 최신 main의 COM 자동 연동을 유지했으며 새 Windows 배포 ZIP은 만들지 않았다. 배포자는 검증 후 확정한 동일 커밋의 전체 소스 또는 전체 전달 폴더를 Windows 담당자에게 제공한다. 받는 위치·필수 폴더·실행·연결 JSON 가져오기는 [현재 가이드](../gui_test/TEST_BOARD_CONNECTOR_GUI.md#어디서-받아-실행하는가)를 따른다. Linux 플러그인 설치가 Windows 자동 다운로드·설치를 수행한다고 안내하지 않는다. Windows 기본 진입점은 루트 `board-connector.cmd`다.

현재 GUI는 PORT-009, 선택적 고급 CLI 번들은 PORT-008을 적용한다. `scripts/setup.*`/CLI `launch.cmd`/과거 EXE를 GUI의 기본 실행 단계로 섞지 않는다. 이번 파일명·새 번들 출력명·호환성·복원과 검증은 [PORT-009](../porting/PORT-009.md), [PORT-008](../porting/PORT-008.md), [실행 기록](../testing/runs/20261117-connector-cleanup.md)을 함께 전달한다. 기존 `windows-runner.json`·API `runner` 값·home·실행 기록은 그대로 유지한다. 회사 적용과 실제 Windows/SSH/장비 인수는 별도다.

## 2026-11-16 · 이전 설치본 재사용과 갱신 명령

수정 코드·시험 기준은 `0c98758e96315e376115b5ea58a8ca4ac6eae79c`다.

Agent Monitor 담당자는 `run.sh`와 `apps/agent-monitor/manage.py` 및 manager/lifecycle 시험을 적용한다. 소스를 갱신한 뒤 일반 start가 기존 API를 재사용하는 경로를 안내하고 `./run.sh restart`로 UI·설치본·API·Worker 갱신을 처리한다.

플러그인 담당자는 복사형 패키지를 갱신하고 새 버전 적용 시 `manage.py restart --source PACKAGE`를 호출한다. 저장된 포트와 runtime을 사용하며 상태·release·종료 보류 이유를 표시한다. [PORT-007](../porting/PORT-007.md#2026-11-16--설치본-갱신과-재시작), [검증 기록](../testing/runs/20261116-monitor-restart.md).


## 2026-11-16 · 실행 도구 정리와 Claude 별도 세션 리뷰

수정 코드·시험 기준은 `9f30b2b0294e413fc8364d790d5c8b1f59adcff1`다.

플러그인 담당자는 복사형 Agent Monitor 패키지와 도구 설치·설정 목록을 Claude/OpenCode 기준으로 갱신한다. 구현은 OpenCode 기본·난항 시 Claude Opus 전환이고 리뷰는 항상 Claude의 별도 세션이다. 구현 세션의 완료 보고를 리뷰 통과로 재사용하지 않는다.

Agent Monitor 담당자는 설정 화면·설정 정규화·CLI 어댑터·capability·배정·결과 검증을 함께 적용하고 UI를 다시 빌드한다. 이전 설정은 자동 정리되며 작업·시험 이력은 보존한다. 적용 파일·이전 데이터·검증 절차는 [PORT-007](../porting/PORT-007.md#2026-11-16--claude-별도-세션-리뷰), [보고 계약](../design/AGENT_STATUS_CONTRACT.md), [실행 기록](../testing/runs/20261116-claude-review.md)을 따른다.


## 2026-11-16 · 초기화 시 미완료 BSP 기록 정리

수정 코드·시험 기준은 `79ef92852f7a8a5e8aadf6ed48870100ccbc3310`다.

기존 `ef9edbe`는 TC를 취소한 뒤에도 최종 검토가 없는 BSP 작업이 일반 stop을 막았다. Agent Monitor 담당자는 `manage.py`의 reset_runtime/공통 process 종료 판정, `recovery.py`의 archive_idle_records/reset_plan과 recovery/live 회귀 시험을 적용한다. 플러그인은 같은 관리자를 복사형 패키지에 포함하고 기존 reset 호출을 사용한다. JSON 결과의 pre_stop_archives는 최초 runtime 백업 이후, 종료 직전 DB 잠금 안에서 확보한 실행 기록 DB 백업 목록이다. 최초 backup과 함께 복구 화면/운영 기록에 전달한다.

일괄 초기화에서 실행이 없는 BSP 기록은 백업 후 삭제한다. 실제 실행·프로세스·Jira 전송·lease 상태는 잠금 안에서 재확인한다. 일반 stop의 완료 조건은 유지한다. [현재 흐름](PLUGIN_CONTROL_API.md#설정을-유지하는-일괄-초기화), [PORT-007](../porting/PORT-007.md), [같은 오류 재현·재시험](../testing/runs/20261116-reset-bsp.md).


## 2026-11-16 · 실행 중 서비스의 일시정지 세션 초기화 수정

수정 코드·시험 기준은 `17c6c6a2b1895a7f006a1ff7c2caf52b838e9bcf`다.

기존 `625c6ce`의 reset은 일반 stop을 먼저 요청하여 PAUSED 예약에서 중단됐다. Agent Monitor 담당자는 `apps/agent-monitor/manage.py`, `recovery.py`, recovery 시험과 새 `tests/test_agent_monitor_reset_live.py`를 적용한다. 플러그인 담당자는 복사형 패키지를 갱신하고 기존 reset 호출과 stdout/stderr 처리를 사용한다. RESET_DRAINING은 백업 후 기존 취소 API로 세션·예약 해제를 기다리는 상태다. 같은 reset 명령은 원래 백업을 유지하며 이어서 처리한다.

이미 실행 중인 관리자는 기존 API와 일반 stop으로 연결한다. 새 전용 API 설치나 수동 세션별 취소가 필요했던 경로를 보완했다. [범위와 조건](PLUGIN_CONTROL_API.md#설정을-유지하는-일괄-초기화), [PORT-007](../porting/PORT-007.md), [수정 전 재현과 실제 HTTP 회귀](../testing/runs/20261116-reset-live.md).


## 2026-11-16 · 설정 유지 일괄 초기화

코드·시험 고정 커밋은 `226c3f2db3d67e374d5b303b168b4248a1177ea1`다.

Agent Monitor 담당자는 `run.sh`, `apps/agent-monitor/manage.py`, `recovery.py`와 lifecycle/recovery 시험을 적용한다. 플러그인 담당자는 복사형 설치 패키지에 같은 코드를 포함하고 사용자가 초기화를 선택했을 때 `manage.py reset`을 호출한다. 시작 과정의 오류 처리를 초기화로 자동 전환하지 않는다. 성공 JSON의 state=RESET과 backup 정보를 표시하고 캐시한 세션·시험 목록을 다시 조회한다. 실패는 stderr의 RESET_BLOCKED/RESET_PENDING 안내를 표시한다. [명령과 범위](PLUGIN_CONTROL_API.md#설정을-유지하는-일괄-초기화), [PORT-007](../porting/PORT-007.md), [검증](../testing/runs/20261116-runtime-reset.md).


## 2026-11-16 · 일시정지 예약을 유지하는 최초 이관

코드·시험 고정 커밋은 `dc646490656ae6a05d5ba00eb0f60e5b6f929cc5`다.

Agent Monitor 담당자는 `apps/agent-monitor/manage.py`, `recovery.py`, `tests/test_agent_monitor_recovery.py`를 적용한다. 플러그인 담당자는 복사형 패키지에 같은 코드를 포함하고 기존 start 명령을 사용한다. 최초 설치의 검증된 PAUSED 예약은 자동 백업 후 기존 runtime으로 연결된다. 기존 세션 제어와 예약 소유권을 유지하고, 종료 근거 부족·UNKNOWN·진행 중 플래싱 등은 보류 코드를 표시한다. [PORT-007](../porting/PORT-007.md), [사용 조건](PLUGIN_CONTROL_API.md#기존-runtime-검사최초-이관복원), [검증](../testing/runs/20261116-paused-adoption.md).


## 2026-11-16 · 한 명령 runtime 진단

수정 코드·시험 기준은 `aa25c1b17e0039ed6ddc9bb3c11c106022487d0f`다.

Agent Monitor 담당자는 `run.sh`, `apps/agent-monitor/manage.py`, `recovery.py`와 manager lifecycle/recovery 시험을 적용한다. 플러그인 담당자는 복사형 배포본에 같은 코드를 포함하고 최초 이관 보류 시 자동 출력되는 진단을 화면에 전달한다. 독립 진단은 `bash run.sh doctor`이며 `manage.py doctor`의 stdout은 상태 코드·건수 JSON, stderr는 사용자 안내다. 실제 예약 개수와 HELD_RESERVATIONS 차단 항목 수를 구분한다. [사용 안내](PLUGIN_CONTROL_API.md#기존-runtime-검사최초-이관복원), [검증](../testing/runs/20261116-runtime-doctor.md).


## 2026-11-16 · Agent Monitor 설치 대기 표시

수정 코드·시험 기준은 `0824070078b77f5d8eba9e4a556dce5238b55f2f`다.

Agent Monitor 담당자는 `apps/agent-monitor/manage.py`와 `tests/test_agent_monitor_manager.py`를 적용한다. 플러그인 담당자는 복사형 패키지에 같은 관리자를 포함하고 stderr의 설치 단계·10초 간격 경과 시간·실패 안내를 설치 화면에 전달한다. 명령 결과는 stdout JSON으로 읽는다. 상세 로그는 회사 PC의 설치 home에 보관한다. [설치 안내](PLUGIN_CONTROL_API.md#설치공개-필수-도구-준비), [검증](../testing/runs/20261116-monitor-install-progress.md).


## 2026-11-16 · Linux UI 빌드 진행 표시

적용 코드·시험 기준은 `7ef37a36226a593de4227687b91ed17039fc124a`다.

Agent Monitor 담당자는 `scripts/build-ui.sh`와 `tests/test_build_entrypoint.py`를 적용한다. 소스에서 UI를 빌드하는 플러그인 담당자는 같은 스크립트를 사용하고 설치·컴파일 단계 출력과 오류 종료 코드를 전달한다. 빌드된 자산을 포함한 배포본은 기존 설치 절차를 따른다. [실행 기록](../testing/runs/20261116-build-progress.md), [실행 명령](../../scripts/README.md).


## 2026-11-16 · Claude 2.1.317 환경 점검 수정

수정 코드·시험 기준은 `99abc6106794b4a332e88f9a0b026231bbc9832d`다.

Agent Monitor 담당자는 `backend/adapters/native.py`와 `tests/test_native.py`를 적용하고 API·Worker를 재시작한 뒤 환경 점검을 다시 실행한다. 플러그인 담당자는 복사형 Agent Monitor 패키지에 같은 수정 코드를 포함하고, 환경 점검에서 반환하는 버전·미확인 옵션 안내를 사용자에게 전달한다. 적용 근거와 시험 범위는 [수정 기록](../testing/runs/20261116-claude-probe.md), 사용 절차는 [환경 안내](ENVIRONMENT_AND_BRIDGES.md#claude-21317-환경-점검-오류)를 따른다.


## 후속 설계 자료 · 2026-11-15 추가 확인

[제한시간120초·제품 Mock 제거·공통 설정 갱신 설계](../design/TEST_TIMEOUT_SYNC_PLAN.md)를 추가로 전달한다. **설계 자료이며 제품 적용 완료 요청이 아니다.** 이번 게시로 플러그인·Agent Monitor·Windows의 실행 코드를 변경하지 않는다. 플러그인 담당자는 향후 공통 설정 API 소비·재조회 조건을, Agent Monitor 담당자는 시간 헤더·단일 설정 controller·Mock 제거와 기존 데이터 보존 범위를 검토한다. 현재 적용할 완성 코드는 아래 보드 커넥터 미러 요청과 고정 기준을 유지한다.

## 2026-11-15 최신 요청 · 보드 커넥터 미러

적용 코드 기준: `c4d7664653a2ae884736e9b9824908f899b771b0`. 이전 화면·PuTTY·RQ-69 변경을 포함한다. 이번 요청은 RQ-70/D-75이며 [미러 계약](../design/BOARD_CONNECTOR_MIRROR.md), [PORT-009](../porting/PORT-009.md), [검증](../testing/runs/20261115-connector-mirror.md)을 먼저 확인한다.

**플러그인 담당자에게 전달할 요청**

> Agent Monitor 보드 커넥터 미러 계약을 적용해 주세요. `PluginClient.connector_mirror`, `connector_command`, `connector_command_receipt`, `acknowledge_unknown_connector_command`를 공통 Linux 서비스에 연결하세요. 기존 runtime/package pin, 동일 의도의 idempotency key와 설정 CAS를 유지하세요. 설정 저장과 Windows 적용 receipt를 구분하고 EXPIRED/UNKNOWN을 자동 재실행하지 마세요. Windows 앱 자동 시작 등록이나 별도 TC 실행기는 추가하지 않습니다. 최초 Windows 연결은 기존 bootstrap 전달 방식을 유지합니다. 회사 분석기·ACON 어댑터는 이 API를 사용하고 회사 적용 이력은 COMPANY_MAP/APPLIED에 기록하세요.

**Agent Monitor·Linux 서버 담당자에게 전달할 요청**

> PORT-007/009에 따라 `ConnectorMirror`와 live 전용 host를 보드 커넥터 탭에 연결하세요. `connector/mirror` 상태·명령 API와 기존 shared settings를 함께 적용하고, 상태 게시/claim/receipt의 non-browser 경계와 브라우저 권한·CSRF를 유지하세요. 기존 단일 Worker를 재사용하세요. 보드별 로그, 최신 오류, 실제 적용 확인, 동시 편집 충돌, 결과 불명 확인을 표시하세요. Windows 구성 요소도 같은 기준으로 갱신해야 합니다.

**Windows 담당자 적용 범위**

`connector/mirror_client.py`, `mirror.py`, `supervisor.py`, `shared_control.py`, `settings.py`, `web_actions.py`와 해당 의존 코드를 같이 갱신한다. 실행은 기존 `board-connector.cmd`다. 실행 중 TC를 끝내고 커넥터를 종료한 뒤 갱신·재실행하며 기존 설정/runtime은 보존한다. SSH 키·TC 파일·새 EXE·배포 ZIP은 이식 대상에 넣지 않는다.

로컬 Python·브라우저·빌드 결과는 검증 기록을 따른다. 실제 회사 Windows 11/Python 3.13·SSH·UART·PuTTY 인수 T-269는 NOT_RUN이다.

## 최신 커넥터 화면·PuTTY 후속 · D-74

2026-11-15 최신 적용 코드·시험 커밋은 `bb803c3846a554acc39a9272beb466814429b286`다. RQ-69 최초 연결·프로파일 보완도 포함한다. 아래 요청문을 플러그인·Agent Monitor/대시보드 담당자와 Windows 담당자에게 함께 전달한다.

```text
원본 저장소: https://github.com/graycoral/bsp_os_upgrade_dashboard
적용 기준: bb803c3846a554acc39a9272beb466814429b286

회사 필수 지침과 기존 추가 기능을 보존하고 다음 문서의 코드·시험을 재사용해 적용해 주세요.
1. docs/agents/BSP_UPGRADE_PLUGIN_REQUEST.md의 최신 D-74 및 RQ-69 담당별 항목
2. docs/porting/PORT-007.md와 PORT-009.md, 회사 COMPANY_MAP.md/APPLIED.md
3. docs/agents/PLUGIN_CONTROL_API.md와 보드 커넥터 사용 가이드

플러그인/대시보드: RQ-69 최초 연결·프로파일·공통 제어와 기존 단일 Worker/보드 콘솔을 연결합니다.
Windows: 같은 버전의 Manager·Host·브라우저 자산을 함께 적용합니다.
PuTTY 열기에서 입력 제어권을 자동 취득하고 창 종료/실행 실패/반환 통신 회복 시 반환합니다.
별도 수동 제어 버튼이나 UART writer를 만들지 않습니다.
기존 home·SSH 키·보드/TC 설정·실행/UNKNOWN 기록을 보존합니다.

현재 커넥터 화면은 같은 커밋의 격리 환경에서 Chromium15 PASS입니다. Python95와 Astra 승인은 기존 PuTTY/REG-0092 근거이며 이번 화면 변경의 신규 독립 리뷰는 아닙니다. 실제 회사 인수는 별도입니다.
회사에서는 실제 SSH/등록, 멀티 COM, PuTTY 입력과 보드 콘솔 동시 수신, 창 종료 후 TC 재개를 확인하고 적용 이력을 남겨 주세요.
```

상태등과 같은 줄의 설정/전원, PuTTY 아이콘·목록 대수, 기본 보드 현황/설정 복귀와 시험 중 상태등 효과를 포함한다. 이번 후속은 아래 RQ-69 게시 기준을 이어받는다. 보드 커넥터의 브라우저 자산·Manager·Host를 같은 버전으로 적용한다. PuTTY 열기에서 입력 제어권을 받고 창 종료/실행 실패에 반환하며 별도 수동 버튼은 없다. 로그 조회는 기존 공통 보드 콘솔을 유지한다. 회사 플러그인/대시보드가 별도 UART writer나 중복 Worker를 만들지 않는다.

- 플러그인/대시보드 담당자: 아래 RQ-69 전달 절차와 [공개 API 후속](PLUGIN_CONTROL_API.md), [PORT-007](../porting/PORT-007.md)을 따른다. 이번 화면 변경에 필요한 새 Linux API는 없다.
- Windows 담당자: [PORT-009 최신 후속](../porting/PORT-009.md) → [사용 가이드](../gui_test/TEST_BOARD_CONNECTOR_GUI.md#putty) → [T-265/266 검증](../testing/runs/20261114-connector-putty.md)을 적용한다. 기존 home/키/COM/TC 설정과 기록은 유지한다.

회사 전달 시 이 요청서의 최신 고정 커밋과 PORT-007/009·API 안내를 같은 소스 버전으로 공유한다. 실제 Windows·PuTTY·UART·SSH·TC 인수는 회사에서 수행하고 COMPANY_MAP.md/APPLIED.md에 남긴다.


## 이번 후속 전달 상태 · RQ-69

전체 흐름 재검토에서 초기 연결 정보·실행 프로파일 준비 등 공통 누락을 확인해 보완했다. 관련 Python 1145 PASS/19 SKIP, 브라우저 6 PASS와 독립 리뷰 APPROVED를 확인했다. 실제 플랫폼/장비 인수와 Mac 환경 실패는 실행 기록에서 구분한다. [현재 구현/검증](../testing/runs/20261114-plugin-flow-implementation.md), [독립 리뷰](../testing/runs/20261114-plugin-flow-audit.md), [최신 API 절차](PLUGIN_CONTROL_API.md)를 먼저 읽는다. 이번 후속의 코드·시험 고정 커밋은 `bfb7a21075d2bc7f44f414e087179720cdd3dd5c`다. **아래 과거 고정 커밋만 복사하면 이번 보완은 포함되지 않는다.**

### 담당별 업데이트 항목

| 대상 | 적용할 변경 | 상세 문서 |
|---|---|---|
| 회사 플러그인 | 기존 서버·SSH 계정·포트로 최초 연결 JSON 생성, 중앙 TC/이미지 경로 설정, 명령·플래싱 프로파일 준비와 적용 확인, 로그·오류·삭제 연결, BSP 작업의 BspPluginClient 사용 | [공개 API·절차](PLUGIN_CONTROL_API.md), [PORT-007](../porting/PORT-007.md) |
| Agent Monitor 대시보드·Linux 서버 | bootstrap/profiles/삭제 API 등록, 요청별 서비스 identity 확인, 동일 중앙 설정·단일 Worker 유지, 단독 화면 저장 공간 편집 권한, 플래싱 분석 근거 전달, 콘솔 최신성 확인, 전체 호스트 BSP scope 반영 | [PORT-007 담당별 적용](../porting/PORT-007.md#담당별-적용-범위--rq-69) |
| 보드 커넥터 | 연결 JSON 가져오기·파일 선택, 기존 키/보드 설정 보존, 프로파일 안전 적용·실제 Host revision 보고, 고정된 Linux identity로 요청 | [PORT-009](../porting/PORT-009.md), [사용 가이드](../gui_test/TEST_BOARD_CONNECTOR_GUI.md) |

원본의 공통 구현과 문서는 수정했다. 회사 플러그인·회사 대시보드 저장소에는 아직 적용하지 않았다. 아래 요청문과 고정 커밋 `bfb7a21075d2bc7f44f414e087179720cdd3dd5c`를 함께 전달한다.

```text
회사 플러그인과 Agent Monitor를 다음과 같이 함께 갱신해 주세요.
원본 저장소: https://github.com/graycoral/bsp_os_upgrade_dashboard
코드·시험 고정 커밋: bfb7a21075d2bc7f44f414e087179720cdd3dd5c
최신 전달 문서의 담당별 항목을 함께 적용해 주세요.

[플러그인]
- 기존 Linux 서버·SSH 계정·포트로 connector-bootstrap 연결 파일을 생성합니다.
- TC/이미지 경로는 중앙 settings에 저장하고 Windows에 반복 입력하지 않습니다.
- command/flash profiles API로 실행 설정을 준비하고 Windows 실제 적용 revision을 확인합니다.
- PluginClient의 로그·오류·세션 삭제와 BspPluginClient의 전체 BSP 작업 제어를 연결합니다.

[Agent Monitor 대시보드·Linux 서버]
- bootstrap/profiles/삭제 API와 요청별 runtime/package 확인을 반영합니다.
- 같은 중앙 설정과 기존 Worker 하나를 사용합니다.
- 단독 화면의 저장 공간 편집 권한, 플래싱 실패 분석 근거, 콘솔 최신성 검사를 반영합니다.
- 전체 호스트의 bsp-control-v1 범위를 연결하고 기존 운영 게이트를 유지합니다.

[보드 커넥터]
- 연결 파일 가져오기와 프로파일 안전 적용·실제 Host revision 보고를 함께 갱신합니다.
- 기존 SSH 키·보드 설정·진행/UNKNOWN 기록을 보존합니다.

정확한 인터페이스·파일·시험은 docs/agents/PLUGIN_CONTROL_API.md와 PORT-007/009를 따릅니다.
회사 적용 위치와 검증 결과는 COMPANY_MAP.md/APPLIED.md에 기록합니다.
```

## 직전 게시 이력 · 2026-11-14

제품명 **Agent Monitor**, 설명 **bsp-os-upgrade**. 원본 구현·문서는 게시되어 있다. 적용 기준은 `5ca4d8df925fbb329048322f4e7635b575265110`, 제품·시험 커밋은 `475e285cc35765b29470348b581194aa03c47677`이다. 적용 기준에는 보드 커넥터 미리보기·간략 화면 후속 수정도 포함한다.

[최종 검증](../testing/runs/20261114-remaining-implementation.md): Python 1,009 PASS/24 플랫폼 SKIP, 브라우저 13+6 PASS, 두 UI 빌드 PASS. [별도 코드 리뷰](../testing/runs/20261114-remaining-code-review.md)는 APPROVED다. 회사 플러그인·ACON 연결과 실제 설치·장비 인수는 별도다.

**다음 코드 블록은 직전 게시 이력이다. 새 전달에는 위 담당별 요청문과 새 고정 커밋을 사용한다.** 적용 담당자가 지정 커밋의 문서·코드·시험을 읽을 수 있어야 한다. 저장소에 접근할 수 없다면 같은 커밋의 전체 소스 또는 검증된 전달 폴더를 함께 제공한다.

### 직전 게시 버전 요청문 · 이력

```text
회사 bsp-upgrade 플러그인에 Agent Monitor와 보드 커넥터를 연동해 주세요.
제품명은 Agent Monitor, 설명은 bsp-os-upgrade입니다.

원본 저장소: https://github.com/graycoral/bsp_os_upgrade_dashboard
적용 기준: 5ca4d8df925fbb329048322f4e7635b575265110
제품·시험 커밋: 475e285cc35765b29470348b581194aa03c47677
원본 구현과 문서는 게시되어 있습니다. 위 기준의 문서·코드·시험을 함께 사용해 주세요.

회사 필수 지침을 먼저 확인하고 다음 순서로 읽어 주세요.
1. docs/porting/PORT-007.md와 회사 COMPANY_MAP.md/APPLIED.md
2. docs/agents/PLUGIN_CONTROL_API.md
3. docs/porting/PORT-009.md와 해당 코드·시험
4. docs/testing/runs/20261114-remaining-implementation.md
   docs/testing/runs/20261114-remaining-code-review.md
문서의 과거 미커밋·읽기 전용 한정·PASS 2회 정책은 당시 이력입니다.
최신 절의 고정 커밋과 새 Run 정책을 적용해 주세요.

전체 Agent Monitor 전달 폴더의 설치 관리자와 PluginClient를 재사용하고,
회사 설치 hook·ACON/UI·분석 호출·신뢰된 조치 검증 adapter를 연결해 주세요.
플러그인이 중심이며 실제 배정은 기존 상주 Worker 하나가 맡습니다.
Agent Monitor와 보드 커넥터는 같은 설정·상태·콘솔 로그·오류를 사용하고,
화면을 닫아도 TC가 계속되어야 합니다. 실행 엔진이나 설정 원본을 중복 생성하지 마세요.

이미지 플래싱부터 부팅 확인·TC 실행까지 기존 서버/커넥터 경로를 재사용해 주세요.
플러그인은 Linux 기준 설치 BAT·TC 경로를 지정하고, 서버가 Windows 전달을 처리합니다.
보드 커넥터에는 선택된 서버 경로와 실제 실행 경로를 표시합니다.
회사 PC의 연결 정보를 재사용하고 같은 내용을 보드마다 반복 입력하게 하지 마세요.

TC 기본 제한시간은 600초이며 명시한 개별값과 실행 중 고정 설정을 보존합니다.
첫 실패 시 해당 Run의 후속 TC를 멈추고 플러그인에서 분석합니다.
조치와 프로세스 종료·보드·입력·현재 BSP 조건을 검증한 뒤 자동 재실행하며,
같은 원인 재발 시 중단합니다. 기본 진단이나 검증기 부재 상태는 HOLD입니다.
회사 분석·검증 프로그램을 연결하고, 내장 소비자 또는 외부 플러그인 소비자 중
하나를 선택해 주세요. 기존 Run 정책·UNKNOWN·BSP 운영 게이트를 유지해 주세요.

공통 설정·제한시간·캐시 정리 정책은 공개 API와 제공된 JSON 편집 경로를 사용합니다.
자동 정리는 기본 7일·호스트별 20 GiB이며 진행 작업과 실패 근거를 보호합니다.
공개 필수 도구 준비, runtime 검사·이관·롤백·release 정리 명령을 재사용해 주세요.
회사 드라이버·TC 패키지는 회사가 제공한 서명/해시·공급 경로로 연결해 주세요.
Windows 진입점은 board-connector.cmd이며 Python 3.13을 우선 사용합니다.
새 EXE를 만들거나 웹 재빌드마다 커넥터를 재설치하도록 구성하지 마세요.

회사 backend·runtime·설정·기존 기능을 보존하고 독립 설치 경로에 적용해 주세요.
원본/회사 커밋, 파일 manifest, 연결 위치와 차이를 COMPANY_MAP/APPLIED에 기록하고,
실제 Linux/Windows 11·Python 3.13·SSH·COM·fastboot·플래싱·TC·분석기·ACON·복원을
회사 정책과 승인된 장비 범위에서 검증해 주세요. 로컬 모의 PASS와 회사 인수를 구분하고,
미실행 항목은 T-256 NOT_RUN으로 기록해 주세요.
```

아래는 과거 적용 이력이며 추가로 복사할 요청문이 아니다.

## 기존 구현 전달 이력 · 2026-11-07 이후

후속 CLI 번들 인계는 [PORT-008](../porting/PORT-008.md), [실행 안내](../gui_test/BOARD_CONNECTOR_BUNDLE.md)를 따른다. 회사 고유 경로·플러그인 등록·UI hook은 회사에서 연결하며 재사용 백엔드 기능과 계약은 유지한다. 실제 회사 인수는 별도다.

RQ-60 / D-64 · 2026-11-07 · **원본 로컬 구현·모의 검증 / 회사 적용 별도**

재사용 backend·Runner·참조 client·headless/선택 UI 패키징의 고정 소스 커밋은 `1a18ea6fab8b1caead3935ce70cb1e30153d631b`이다. 현재 공개 진입점과 CLI·브라우저 인증·연결 실패 로그는 [설계 §13~14](../design/BSP_UPGRADE_PLUGIN_INTEGRATION.md#13-후속-구현의-공개-진입점과-선택-화면)를 따른다. 로컬 모의 검증과 회사 인수 상태는 PORT-007과 실행 기록을 따른다. 회사 private 플러그인 적용과 실제 장비 인수 T-209는 별도이며 NOT_RUN이다.

회사 plugin 코드는 새 실행 엔진을 작성하지 않고 `standalone.plugin_client.PluginClient`를 기존 HTTP/설치 adapter에 매핑한다. 연결 버튼/시작 준비에서는 `connect()`, 모듈 기본값은 `PatternDefaults.suggest` 또는 회사 설정 저장소와 동일한 `resolve_patterns`, 실행에는 stable key를 보관한 `start`, 상태에는 `run(id)`, 선택 상세 화면에는 `browser_access()`를 사용한다. 소스 import는 `backend.gui_test`, wheel import는 `gui_test`다. `diagnostic_callback`과 `last_diagnostic`을 상태 UI에 표시하고 `log_dir`를 회사 로컬 로그 정책 경로로 지정한다. 연결 실패의 correlation ID·원인·조치·로그 경로가 API 수락 전에도 보이도록 유지한다. 실제 private plugin 파일 위치는 COMPANY_MAP에 기록한다.

아래 요청문은 회사 플러그인 담당자에게 범위와 연결 책임을 전달하기 위한 것이다. API·데이터·흐름의 원문은 [연동 설계](../design/BSP_UPGRADE_PLUGIN_INTEGRATION.md), 전달 상태는 [PORT-007](../porting/PORT-007.md)을 따른다. 요청문에 API 스키마나 결과 형식을 따로 복제하지 않는다.

## 담당별 읽기와 구현 순서

| 담당 | 읽을 문서·절 | 구현/적용할 범위 |
|---|---|---|
| 회사 플러그인 개발자 | 이 요청서 → 연동 설계 §1 확정 경계, §3 서비스 수명, §4 요청/조회, §5 패턴/준비 token, §11 책임, §12 예외 | 모듈 기본값 저장, 미리보기/편집, 서비스 health/start adapter, 멱등 키·준비 token·Run ID 저장, 기존 결과 링크. 새 퓨징/TC 엔진은 만들지 않는다. |
| 회사 대시보드/백엔드 담당 | PORT-007 → 회사 COMPANY_MAP/APPLIED → 연동 설계 §2 현재 소스, §6~10 실행/안전/저장, §11 패키징 | 검증된 원본 API/core/Windows adapter를 재사용하고 회사 인증·서비스·DB/runtime·선택 UI mount를 연결한다. |
| 회사 배포/장비 담당 | 연동 설계 §3, §6~7, §9~10, §12와 PORT-007 인수 조건 | 기본 보드/COM·TC 명령/소스, BAT 등록·타깃/실패 전파, 터널·Runner·splitter·권한 설정. T-209 실제 환경 인수. |

회사 플러그인 코드는 현재 이 저장소에서 확인할 수 없으므로 설치 hook·사내 구조는 회사 adapter에서 연결한다. 사용 순서는 [PORT-007의 절차](../porting/PORT-007.md#회사-적용과-사용-순서)와 [회사 안내서](../gui_test/BSP_UPGRADE_COMPANY_GUIDE.md)를 따른다.

## 과거 요청문 · 2026-11-07 · 현재 전달에 사용하지 않음

```text
회사 Linux에서 사용하는 bsp-upgrade 플러그인에 GUI Test 연동을 준비해 주세요.
원본 구현과 로컬 모의 검증을 수행했으며 회사 적용과 실제 인수는 별도입니다.
고정 소스와 검증된 최종 전달물의 상태를 PORT-007에서 확인해 주세요.
회사의 필수 지침을 먼저 확인하고 원본 문서의 확정 요구,
제안 기본값, 현재 구현된 동작을 구분해 주세요.

기준 문서:
- docs/design/BSP_UPGRADE_PLUGIN_INTEGRATION.md
- docs/porting/PORT-007.md

플러그인 설치물에는 이 저장소에서 구현·검증할 GUI Test 백엔드와
선택적 GUI 화면을 포함합니다. 실행 엔진은 기존 GUI Test를 재사용하고,
플러그인은 서비스 확인·기동과 HTTP 요청/조회에 집중해 주세요.
백엔드/worker·SSH 터널·보드 커넥터는 플러그인 호출이나 브라우저가
끝나도 유지되어야 합니다. 같은 runtime에 worker를 중복 기동하지 마세요.

플러그인에서는 Linux installer BAT 경로와 최종 TC 패턴을 전달합니다.
모듈별 기본 TC 패턴과 전역 기본값을 저장하고 안정적인 모듈 키로 추천해 주세요.
사용자는 실행 전 패턴·일치 TC·순서를 미리 보고 변경할 수 있어야 하며,
실행마다 별도 승인 창을 강제하지 마세요. 이번 실행의 변경과 기본값 저장을
구분하고, 재조회로 사용자 편집을 덮어쓰지 마세요. 미리 본 파일과 설정은
준비 token으로 시작 요청에 연결하고, 미리보기 없는 요청도 같은 준비를
자동 수행하도록 해 주세요. token 오류 때 다른 파일로 조용히 바꾸지 마세요.

실제 COM·보드·TC 실행 명령·TC 소스 루트·Runner 주소는 서비스 설정을
재사용합니다. 플러그인에서 임의 셸 명령·COM·비밀정보를 요청 본문으로
전달하지 마세요. 플러그인 모듈 정보는 추천용이며 내부 BSP의 운영
module_context나 장비 시험 완료 권한으로 사용하지 마세요.

시작은 비동기 HTTP 요청으로 하고 반환된 기존 Run 식별자를 저장합니다.
응답 유실·재접속에는 같은 멱등 키를 사용하고, 기존 Run 조회와 보고서를
재사용해 주세요. 콜백·별도 결과 포맷·플러그인의 PASS 등록 API는 필요 없습니다.

installer 폴더 전체 복사, TC 루트 전체 의존성 전달, 사전 검사와 장비 예약,
reboot lkshell → fast → BAT → 새 로그인 프롬프트 → TC 로그인,
최대3회/PASS2 정책과 panic/부팅 실패 중단은 백엔드 구현 책임입니다.
플러그인에 이를 중복 구현하지 마세요. 자세한 판정·예약·로그 계약은
연동 설계 원문을 사용해 주세요.

GUI 전용 연동 호스트와 Windows adapter를 고정 원본에서 재사용하고,
수정된 퓨징 감독 경로와 전체 batch 예약 계약을 함께 반입해 주세요.
실제 공개 진입점과 제한은 연동 설계 §13~14를 확인해 주세요.

회사에서는 설치 hook·서비스 관리자·인증·허용 경로·기본 보드·COM,
저장된 TC 명령·TC 루트·실제 모듈 매핑·터널과 Runner의 지속 실행,
승인된 RX-only COM splitter 및 실제 BAT/TC의 준비 조건을 확인해 주세요.
BAT는 처음과 변경 시에 타깃 serial 준수·실패 전파를 등록하고 이후 동일
스크립트는 자동 hash 검증합니다. 매 TC마다 사람 승인을 반복하지 마세요.
비밀정보는 회사의 로컬 보안 설정으로 관리하고 공유 문서에 쓰지 마세요.

회사 구조 차이는 COMPANY_MAP.md에, 적용 범위·커밋·검증·미완료는
APPLIED.md에 기록합니다. 기존 회사 기능과 설정을 보존하세요.
회사 적용과 실제 장비 인수는 각각의 검증 증거가 생길 때 기록해 주세요.
```

## 담당자 간 전달물

| 원본 저장소 담당 | 회사 플러그인/호스트 담당 |
|---|---|
| 기존 엔진에 연동 API·headless 호스트·준비/퓨징/정책·로그를 구현하고 계약 시험 제공 | 설치·서비스 조립 차이와 플러그인 설정/화면/HTTP 호출 구현 |
| Linux 백엔드와 선택 UI, 별도 보드 커넥터의 검증된 패키지·manifest·고정 커밋 제공 | 회사 의존성/인증/보드/COM/소스/실제 명령·splitter 조건 확인 |
| T-200~208 로컬·모의 결과와 미검증 범위 기록 | 영향 회귀와 T-209 실제 회사 인수 기록 |
| 계약 원문·PORT 갱신 | COMPANY_MAP/APPLIED의 회사 대응·적용 이력 갱신 |

원본의 로컬·모의 검증 결과와 최종 산출물 상태는 PORT-007을 따른다. 실제 회사 인수 T-209는 NOT_RUN이다. 첫 배포 설정과 실제 UNKNOWN 장비 복구는 필요하지만 정상 실행·같은 BAT·각 TC마다 반복 승인을 요구하지 않는다. 회사 전달물 `dist/BSP-GUI-Test-Company-20261107.zip` 안의 `bsp-upgrade-integration-20261107/` 폴더에는 `repository-source.zip`, `bsp-gui-test-integration.zip`, wheel, `BSP-Windows-Runner.zip`, `feature-code.patch`, `START_HERE.md`, `SHA256SUMS.json`, `source-provenance.json`과 선택 검증 로그가 포함된다. 압축 해제 후 `repository-source.zip`의 `docs/gui_test/BSP_UPGRADE_COMPANY_GUIDE.md`부터 읽는다. 회사 대시보드 담당자는 전체 소스를 참고하고 기존 회사 기능과 비교한 뒤 patch의 선택적 반영 여부를 결정한다. 세 설치물의 checksum은 PORT에 있으며 전체 전달물 검증은 동봉 checksum과 출처 기록을 따른다.
## 2026-11-12 · Runner 설정 편의 후속 적용

[PORT-008 후속](../porting/PORT-008.md)의 RQ-62 소스·해시·시험을 확인한다. 플러그인의 HTTP 요청 형식은 유지한다. 전달하는 편집 Runner의 `src/scripts/setup_flashing.py`를 선별 갱신하고, 회사의 다운로드 버전/체크섬 pin이 있는 경우 검증된 새 전달물 기준으로만 바꾼다. 원본 후속 코드는 `55447f87f3241df76a7a110c130252b73b29c941`로 고정했고 새 배포 ZIP은 생성하지 않았으므로 기존 릴리스 pin을 임의로 변경하지 않는다.

회사 설정은 `fastboot init success`를 fast 이후 로그로 구분하고, BAT 자동 리부팅 후 `**** login : `의 `login :`를 `login_prompt`와 observer `login_markers`에 일치시킨다. TC는 해당 프롬프트에서 `root` 로그인을 담당한다. Runner가 TC 전에 로그인하지 않는다. 실제 lkshell 프롬프트·TC 로그인 처리·observer boot/panic 값은 회사에서 확인하며, 사용자 제공 문구만으로 실장비 인수 PASS를 기록하지 않는다. 프로파일을 바꾸면 Runner 정상 재시작과 새 미리 보기가 필요하다. 웹 재빌드만으로 Runner를 교체하지 않는다.

## 2026-11-13 연결 토큰 제거 후속

현재 참조 PluginClient는 연결 토큰 없이 loopback 서버를 호출한다. 회사 적용 시 서버·보드 커넥터·플러그인 클라이언트를 함께 갱신한다. 경로·identity·멱등 키·Run 소유권은 유지한다. 변경 파일·적용 조건·검증 범위는 [PORT-009](../porting/PORT-009.md)를 따른다. 회사 플러그인 UI의 실제 적용 여부는 별도로 확인한다.

## 2026-11-17 · Claude Sonnet 기본과 사용량·시간 전달

[PORT-010](../porting/PORT-010.md)의 고정 코드·시험 기준을 적용한다. Agent Monitor 담당은 정책/어댑터/Worker/API와 빌드한 BSP·TC UI를 함께 반영한다. 플러그인은 새 profile의 기본 구현 도구 Claude·모델 sonnet을 유지하고 OpenCode는 명시 선택으로 전달한다. 기존 고정 job과 명시 모델을 다시 쓰지 않는다. 조회 전용 사용량을 실행/완료 근거로 쓰지 않는다. 회사 적용 후 실제 envelope/과금 대조는 T-277이며 로컬 모의 PASS와 구분한다.

## 2026-11-18 · 모듈 후보와 시작 자동 검사

[PORT-012](../porting/PORT-012.md)의 서버·플러그인 client·Dashboard 공통 UI 변경을 함께 적용한다. 회사 영속 모듈 목록을 `BspPluginClient`의 모듈 게시 API에 매핑하고 연결·목록 변경 시 version CAS로 전달한다. 후보 수신으로 기존 설정/job 모듈을 덮어쓰지 않는다. UI의 사내 Jira 연결/검토 탭은 추후 갱신까지 제거하며 backend 판단/Jira 기록은 유지한다. Test 시작은 기존 서버 Preflight와 예약 검사를 내부 수행하므로 별도 점검 클릭을 요구하지 않는다. 회사 callback과 실제 Linux/Windows·장비 인수는 T-290이며 이번 로컬 모의 PASS로 대체하지 않는다.
