# PORT-007 · BSP 업그레이드 플러그인과 GUI Test 연동

## 2026-11-18 · TC 목록 포함 전달 후속

당시 HTTP 연동의 목록·고정 전달 증거는 [PORT-011 TC 목록 이력](PORT-011.md#2026-11-18--tc-목록-포함-전달-후속)에 있다. PluginClient.connector_test_status와 test list는 공통 경로의 전체 목록을 읽기 전용 조회하며 BAT/TC 준비를 생성하지 않는다. 기존 preview는 실행 대상 선택용이다. source/소유권·공유 설정/Run snapshot은 보존한다.

당시 TC 목록 코드·시험 고정 커밋: `665eeb164dbc756426f17323e2cd5d2c6846455f`. 당시 전달 hash와 안전 갱신은 위 절을 따른다. 현재 전달 형식은 [PORT-011 폴더 절차](PORT-011.md#현재-유효-기준)를 사용한다.

2026-11-18 RQ-74 고정 코드·시험: `3af0f09f24a5e3a754ec7bd645aca8c4e9f3b6ac`. 전달·설정 공유·회사 Git 이동 절차는 [PORT-011](PORT-011.md)을 따른다.

## 2026-11-18 · 플러그인 소유 배포·공통 명령 구현

[PORT-011](PORT-011.md)의 전체 전달 폴더·PluginSession·공유 파일 bridge를 사용한다. 회사 dashboard Git의 보드 커넥터 소스를 plugin Git으로 옮기되 UI 소비자와 단일 서비스/runtime/설정·기록을 보존한다. 명령/상태 감시를 회사에서 다시 작성하지 않는다. Windows 실제 실행 위치와 Git 코드 소유권은 별개다.

## 2026-11-17 · 플러그인 사용자 명령 설계

연결 시 준비 알림·상호 설정 갱신과 리뷰된 명령 권고는 [PORT-011](PORT-011.md)을 따른다. 당시 회사 slash adapter·상태 감시/알림은 미구현이었다. 현재 공통 구현과 회사 연결은 [PORT-011](PORT-011.md#현재-유효-기준)을 따른다.

## 2026-11-17 · 보드 커넥터 자동 COM 공유

TC 실행 요청·COM 인자는 유지한다. 복사형 패키지에 Windows 자동 bootstrap·안전한 설정 이전과 Agent Monitor 설정/UI를 함께 포함한다. RX COM·공통 모듈 import 수동 변경은 요청하지 않는다. 적용 파일·선행 기준·복원·검증은 [PORT-009 자동 멀티플렉서](PORT-009.md#2026-11-17--자동-멀티플렉서), 담당별 조치는 [요청서](../agents/BSP_UPGRADE_PLUGIN_REQUEST.md#2026-11-17--보드-com-멀티플렉서-자동-적용)를 따른다.
## 2026-11-17 · 명시적 강제 종료 후속

RQ-71/D-77/T-271~272/REG-0103. 최신 main 자동 COM 연동을 유지한 코드·시험 고정 커밋은 `b6f1c30fb0ba8a3a13d1b16544fd8c0c0254a0f7`다. 실제 코드/모의 시험과 회사 인수·새 ZIP 게시를 구분한다. `run.sh`/`apps/agent-monitor/manage.py`, `board-connector.cmd`/`scripts/board_connector.py`, `execution/force_stop.py`/`launch.py`, `connector/emergency.py`/`supervisor.py`, `scripts/setup_runtime.py`, 관련 시험과 [강제 종료 안내](../gui_test/FORCE_STOP.md)를 같은 변경 단위로 반영한다. Monitor service receipt의 OS owner/children과 Windows active endpoint의 선택 SSH identity를 함께 제공한다. 기존 endpoint v1·DB/API·설정은 유지하며 새 의존성은 없다.

선행 조건은 기존 Manager/Host·상주 Monitor, Linux pidfd 또는 Windows process handle 권한과 같은 home/runtime이다. 과거 실행본에 OS 소유권/고아 SSH identity가 없으면 추측 종료를 거부한다. 정상 stop/disconnect는 그대로 두고 사용자의 별도 비상 명령에만 연결한다. 창 닫기·설치·일반 오류 복구에 강제 종료를 붙이지 않는다. DB/예약/UNKNOWN을 지우지 않고 부분·탐색 불명은 pending/nonzero로 표시한다. 포트나 모든 Python 프로세스를 대상으로 종료하지 않는다.

복원은 종료 근거 확인 후 이전 코드·동일 home/runtime을 함께 보존하는 방식이다. force-stop pending 기록을 삭제해 복원/재시작을 우회하지 않는다. 이번 코드의 검사와 독립 리뷰는 [실행 기록](../testing/runs/20261117-connector-cleanup.md)을 따르며 실제 Linux/Windows·회사 강제 종료 인수는 NOT_RUN이다. 회사는 배포 pin 확정 후 COMPANY_MAP/APPLIED에 경로 차이·부분 적용·검증을 기록한다.


## 2026-11-16 · 설치본 갱신과 재시작

코드·시험 기준은 `0c98758e96315e376115b5ea58a8ca4ac6eae79c`, 선행 기준은 `a35bcdc078b8e2c64f269b86001c23b0ef792362`다. RQ-68 / T-254 / REG-0101에 해당한다.

Agent Monitor 담당자는 `run.sh`, `apps/agent-monitor/manage.py`의 start(restart=True)·main과 `tests/test_agent_monitor_manager.py`, `test_agent_monitor_lifecycle.py`를 적용한다. 실행 중 일반 start의 재사용 안내와 명시적 restart 경로를 함께 반영한다. Git 소스는 지정된 source의 UI를 먼저 빌드하고 검증된 새 설치본을 준비한다. 종료 확인 후 해당 release를 활성화하며 적용 보류 시 오류를 반환한다.

플러그인 담당자는 같은 관리자를 복사형 패키지에 포함하고 갱신 적용에 `manage.py restart --source PACKAGE`를 호출한다. 배포 manifest가 있는 입력은 미리 빌드한 UI를 사용한다. stdout 상태·release와 stderr 진행·보류 이유를 전달한다. 회사 home/source/runtime 매핑은 COMPANY_MAP과 APPLIED에 기록한다.

DB·설정 형식 변경은 없다. 기존 종료·예약 판정을 유지하고 설치/빌드 실패 시 기존 서비스를 유지한다. rollback은 기존 검증 release 복구 절차를 따른다. [검증과 미실행 범위](../testing/runs/20261116-monitor-restart.md), [호출 계약](../agents/PLUGIN_CONTROL_API.md#설치본-갱신과-재시작).


## 2026-11-16 · Claude 별도 세션 리뷰

수정 코드·시험 기준은 `9f30b2b0294e413fc8364d790d5c8b1f59adcff1`다. 선행 기준은 `e37a75d01bd4741e3b6d7a787543b36315d913aa`이며 RQ-13·RQ-37 / D-76에 해당한다.

### Agent Monitor 적용

- `backend/settings.py`의 Profile·Settings·bridge_defaults에서 Claude/OpenCode 설정과 이전 설정 정규화를 적용한다.
- `backend/adapters/native.py`, `bridge.py`, `capabilities.py`와 `backend/domain/policy.py`, `engine.py`, `reports.py`, `backend/worker/main.py`를 함께 갱신한다. 도구 탐지·실행·배정·결과 접수에서 같은 리뷰 정책을 사용한다.
- `apps/web/src/main.tsx`의 환경설정 도구 목록을 갱신하고 `bash scripts/build-ui.sh dashboard`로 UI를 빌드한다. 관리 설치는 새 배포본으로 갱신한 뒤 API·Worker를 재시작한다.
- 관련 Python 시험과 `tests/e2e/dashboard.spec.ts`, `settings-sync.spec.ts`, `orchestration.spec.ts`를 적용한다. 요구사항·역할 지침·계약과 [검증 기록](../testing/runs/20261116-claude-review.md)을 함께 전달한다.

### 플러그인 적용

복사형 Agent Monitor 패키지에 위 코드·UI·시험을 포함한다. 플러그인이 생성하는 도구 설정과 설치 목록은 Claude/OpenCode만 사용한다. 리뷰 역할은 항상 새 Claude 세션으로 요청하며 구현 세션 재개를 리뷰로 사용하지 않는다. 기존 제어 API의 요청·응답 형식은 그대로 사용한다. 회사 경로·패키징 접점은 COMPANY_MAP과 APPLIED에 기록한다.

### 이전 데이터와 복구

DB 스키마 추가는 없다. 이전 설정의 Codex 항목은 조회·저장 시 제거하고 나머지 설정·버전 비교를 유지한다. 작업 snapshot과 시험 이력의 실제 수행자 기록을 보존한다. 과거 snapshot에 남은 폐기 도구의 실행 요청은 거부하며 해당 작업은 실행 상태를 확인한 뒤 최신 설정으로 새 작업을 만든다. 적용 전 runtime을 백업하고 복구할 때 동일 버전의 코드·UI·runtime 백업을 함께 사용한다.

로컬 모의 CLI·API·브라우저 검증과 실제 회사 Linux·모델·BSP·장비 인수는 [실행 기록](../testing/runs/20261116-claude-review.md)에 구분한다.


## 2026-11-16 · 미완료 BSP 기록의 일괄 초기화

수정 코드·시험 기준은 `79ef92852f7a8a5e8aadf6ed48870100ccbc3310`다.

선행 기준 `ef9edbe99baedaa069273c811270d3ff6ce33555`. `manage.py`의 reset_runtime/reset_backup/has_work, `recovery.py`의 archive_idle_records/process_receipt_stopped/reset_plan과 recovery/live 시험을 함께 적용한다. 플러그인은 reset 결과의 pre_stop_archives를 원래 backup과 함께 전달한다. 기존 공개 실행 명령과 서버 취소 API를 사용한다.

DB schema 변경은 없다. 기존 세션 취소 후 모든 runtime DB의 SQLite BEGIN IMMEDIATE 잠금을 획득하고 실행·lease·Jira/질문/시도/외부 프로세스 종료 근거를 재검사한다. 실행이 없는 BSP 기록과 이전 GUI Test 저장소의 세션·예약은 잠금 안에서 별도 SQLite 백업을 만든 후 삭제한다. 원래 작업 상태는 백업에 보존하며 현재 DB의 실행 기록을 삭제한다. 원래 초기화 receipt에 BSP 백업을 먼저 기록하고 DB별로 commit한다. 부분 실패의 RESET_DRAINING 재시도는 원래 backup과 누적 pre_stop_archives의 해시를 확인한다.

종료 전 DB 백업은 원래 reset 백업 아래 pre-stop-* 폴더에 저장한다. 복원 담당자는 원본 backup과 가장 최근의 각 DB archive를 확인하고, 서비스·Worker를 종료한 복원 절차에서 사용한다. 회사 설치 home/runtime 경로와 적용 시험은 COMPANY_MAP/APPLIED에 기록한다. [원본 검증](../testing/runs/20261116-reset-bsp.md), [사용 계약](../agents/PLUGIN_CONTROL_API.md#설정을-유지하는-일괄-초기화). 실제 회사 Linux·Windows·장비 인수는 NOT_RUN이다.


## 2026-11-16 · 실행 중 PAUSED 예약 초기화 후속

수정 코드·시험 기준은 `17c6c6a2b1895a7f006a1ff7c2caf52b838e9bcf`다.

선행 기준 `625c6ce81d7cf7062de9c18a8ac81f65f6f36865`. `manage.py`의 reset_backup/reset_request/cancel_reset_sessions/reset_runtime, `recovery.py`의 reset_plan·예약 검사·demo-dashboard.db 지원과 두 회귀 시험을 함께 적용한다. 회사 Agent Monitor는 기존 루트 reset 명령을 사용하고 플러그인은 같은 관리자 코드를 배포한다.

관리자 소유권을 health로 확인하고 로컬 live/legacy 취소 API를 사용한다. live 경로를 먼저 처리하며 같은 Run을 중복 취소하지 않는다. CAS/종료·예약 해제 확인 후 기존 stop과 오프라인 DB 초기화를 이어간다. 최초 이관의 PAUSED 전용 조건은 기존 범위를 유지한다. reset의 QUEUED 예약 검사는 실행 중 TC가 없고 소유권이 일치할 때 적용한다.

DB schema 변경은 없다. runtime-reset.json에 RESET_DRAINING 상태를 추가하고 취소 전 백업을 후속 초기화/재시도까지 유지한다. 실행 중 백업은 DB별 SQLite backup으로 확정 WAL을 포함한다. 전역 동시 시점 snapshot이 필요한 회사 복원 절차는 서비스 종료 상태에서 별도로 수행한다. 원본 실패와 재시험은 [실행 기록](../testing/runs/20261116-reset-live.md), 회사 적용 위치는 COMPANY_MAP/APPLIED에 기록한다. 실제 회사 API·Windows·보드 인수는 NOT_RUN이다.


## 2026-11-16 · 설정 유지 일괄 초기화

코드·시험 고정 커밋은 `226c3f2db3d67e374d5b303b168b4248a1177ea1`다.

선행 기준은 `cc19559f204dfdee0547c20b34d5701191c28669`다. `run.sh`의 reset 분기, `manage.py`의 reset_runtime/require_reset_complete와 start/prepare/serve 진입 검사, `recovery.py`의 reset_plan/clear_runtime_records를 함께 적용한다. 공개 CLI의 stdout JSON과 stderr 안내를 플러그인의 명시적 초기화 동작에 연결한다. Agent Monitor 운영자는 `bash run.sh reset`을 사용한다.

DB schema는 유지한다. dashboard.db의 config, runs.db의 설정 documents, 연결 registry를 보존하고 실행 테이블·세션 관련 documents를 비운다. 파일별 초기화 대상과 보류 조건은 [사용 안내](../agents/PLUGIN_CONTROL_API.md#설정을-유지하는-일괄-초기화)를 따른다. SQLite WAL을 포함한 runtime 백업은 설치 home/backups/reset-*에 저장한다. DB별 transaction과 runtime-reset.json의 RESET_PENDING 상태를 함께 적용하며 중단 후 같은 명령으로 이어서 처리한다. 복원은 서비스·Worker를 종료하고 백업 runtime과 초기화 receipt를 기준으로 회사 복원 절차에 따라 수행한다.

회사 플러그인/Agent Monitor 담당자는 설치 home·runtime 선택과 명령 결과 매핑을 COMPANY_MAP/APPLIED에 기록한다. 보드 커넥터의 실행 DB와 외부 TC/이미지 저장소는 독립 저장소다. 회사 서비스 종료·실제 DB 초기화 인수는 NOT_RUN이다. [원본 검증](../testing/runs/20261116-runtime-reset.md).


## 2026-11-16 · 일시정지 예약 유지 이관

선행 기준은 `e7501bc9e2bf37b293e3fe6c4010cc083b40f7c7`의 runtime doctor다. 최초 관리 설치의 하드웨어/모의 PAUSED 예약을 검증하고 기존 runtime을 자동 백업·연결한다. 코드·시험 고정 커밋은 `dc646490656ae6a05d5ba00eb0f60e5b6f929cc5`다.

| 대상 | 원본 변경 위치 | 회사 연결 |
|---|---|---|
| Agent Monitor | `apps/agent-monitor/manage.py`의 activate/record_adoption, `recovery.py`의 inspect/paused_reservation_blocker/reservation_summary | 기존 run.sh와 설치 home/runtime을 사용한다. 소유 run/token·종료 근거·플래싱 상태·Worker 잠금 확인 후 백업/포인터 기록을 적용한다. |
| 플러그인 | 복사형 Agent Monitor 설치 패키지와 start 호출 | 같은 관리 코드를 포함하고 stderr의 검사·백업·이관 안내를 전달한다. stdout 결과와 diagnosis summary의 추가 필드를 처리한다. |
| 검증 | `tests/test_agent_monitor_recovery.py` 및 manager/lifecycle/delivery/setup·GUI Test 회귀 | PAUSED/예약 보존, 백업 실패·포인터 실패 후 재시도, CAS/잠금, UNKNOWN/토큰 불일치/종료 근거 누락 거부를 실행한다. |

DB schema 변경은 없다. 백업은 설치 home의 backups/adoption-*에 저장하며 SQLite WAL의 확정 내용을 포함한다. 기존 예약·세션 기록을 유지한다. 복원은 기존 소스와 runtime 백업, runtime-adoption.json/current.json의 기록을 기준으로 회사 운영 절차에서 수행한다. 회사 고유 경로·인증·TC 파일은 회사 담당자가 보유하고, 적용 커밋·시험 결과는 COMPANY_MAP/APPLIED에 기록한다. [조건과 사용](../agents/PLUGIN_CONTROL_API.md#기존-runtime-검사최초-이관복원), [실행 근거·미검증](../testing/runs/20261116-paused-adoption.md).


## 보드 커넥터 탭 · 2026-11-15

고정 코드 기준 `c4d7664653a2ae884736e9b9824908f899b771b0`. 회사 Agent Monitor에는 `ConnectorMirror`와 live host/폴링을 새 탭으로 연결하고 기존 공통 설정·단일 Worker를 유지한다. Linux API와 Windows Manager도 함께 갱신한다. [PORT-009 최신 미러 절](PORT-009.md), [미러 계약](../design/BOARD_CONNECTOR_MIRROR.md), [담당별 전달 요청](../agents/BSP_UPGRADE_PLUGIN_REQUEST.md)을 적용한다. 로컬 모의 통과와 회사 T-269를 구분한다.

최신 커넥터 후속을 포함한 적용 기준은 `bb803c3846a554acc39a9272beb466814429b286`다. [최신 전달 요청문](../agents/BSP_UPGRADE_PLUGIN_REQUEST.md)의 D-74/RQ-69 절을 함께 사용한다.

2026-11-14 D-74 커넥터 화면·PuTTY 후속: Linux의 기존 공통 보드/콘솔·Worker는 유지하고 Windows Manager/Host/웹 자산을 같은 버전으로 적용한다. 별도 PuTTY 송신 API나 UART 소유자를 추가하지 않는다. [PORT-009](PORT-009.md), [최신 전달 요청문](../agents/BSP_UPGRADE_PLUGIN_REQUEST.md), [T-265/266 검증](../testing/runs/20261114-connector-putty.md)을 함께 전달한다.


## RQ-69 · 최초 설정·전체 흐름 보완

기준 `5775661ddcf7b6f9020fdc9ee058b2a12098f819` 대비 이번 후속의 코드·시험 고정 커밋은 `bfb7a21075d2bc7f44f414e087179720cdd3dd5c`다. 과거 고정 커밋만 적용하면 아래 보완은 포함되지 않는다. [공개 연결/설정 절차](../agents/PLUGIN_CONTROL_API.md), [독립 리뷰](../testing/runs/20261114-plugin-flow-audit.md), [현재 시험](../testing/runs/20261114-plugin-flow-implementation.md)을 함께 적용한다.

- 초기 접속: `core/connector_bootstrap.py`, `connector/bootstrap.py`, 기존 CMD/Python launcher·supervisor·shared_control. 회사가 보유한 Windows에서 접근 가능한 Linux 주소/계정/포트를 export/import에 연결한다. SSH 자격은 로컬 보존한다.
- 실행 프로파일: `core/api integration_profiles.py`, `shared_settings.py`, `Manager.save_document` CAS, Windows Settings/Host/적용 receipt를 함께 반영한다. 프로파일 patch·실제 적용 해시를 생략하지 않는다.
- 공통 요청: `PluginClient`, 양 호스트 middleware의 요청별 identity 확인·단독 화면 권한, `api/router.py` 삭제 경로, `RegisteredWindows` freshness gate와 console receipt CAS를 함께 적용한다.
- 분석/BSP: `analysis_runtime.context`의 제한된 플래싱 근거, `BspPluginClient`와 전체 호스트의 명시 scope를 재사용한다. Engine·Worker/보고 계약을 복제하지 않는다.

### 담당별 적용 범위 · RQ-69

| 담당 | 변경 위치 | 적용 확인 |
|---|---|---|
| 플러그인 | `standalone/plugin_client.py`, `standalone/bsp_plugin_client.py`와 회사 설치·연결 callback | 서버/계정/포트 재사용, 중앙 경로 설정, 프로파일 생성/선택, 고정 identity와 실행 key/Run ID 유지, 로그·오류·삭제 수신 |
| Agent Monitor 서버 | `backend/api/main.py`, `standalone/integration.py`, `api/shared_control.py`, `api/integration_profiles.py`, `api/router.py` | 양 호스트의 실제 API 등록, 요청별 identity, 편집 scope, 완료/소유권을 확인하는 삭제, 전체 호스트에만 BSP scope 제공 |
| Agent Monitor 공통 실행부 | `core/shared_settings.py`, `core/integration_profiles.py`, `core/manager.py`, `standalone/analysis_runtime.py`, `connector/registry.py`·`api.py` | CAS 저장·현재 실행 보존, 단일 Worker, 플래싱/부팅 분석 근거, 등록과 콘솔 최신성 및 지연 응답 거부 |
| 회사 대시보드 화면 연결 | 기존 공통 설정·진행·로그·삭제 UI의 회사 API adapter | 같은 서비스의 저장/실제 적용 상태와 오류를 표시한다. 이번 RQ-69는 공통 API/실행부 보완이며 새 프로파일 전용 화면을 구현했다고 간주하지 않는다 |
| 보드 커넥터 | PORT-009의 launcher·bootstrap·설정·Host·receipt | Linux 서버 변경과 함께 적용하고 기존 로컬 설정·실행 기록을 보존 |

원본 공통 구현 완료와 회사 저장소 반영은 구분한다. 회사 플러그인과 회사 대시보드는 아직 수정하지 않았으며 현지 adapter 연결·적용 이력·실장비 검증이 필요하다.

새 DB 테이블 이전은 없다. 기존 documents와 Windows JSON에 추가 데이터를 저장한다. 기존 설정/로그/실패/UNKNOWN을 보존하고 bootstrap 저장은 backup을 만든다. 롤백은 안전 종료·동일 runtime 보존 후 코드/설정 백업을 함께 복구한다. 구버전에는 새 프로파일·bootstrap 지원이 없으므로 운영 중 즉시 교체하지 않는다. 실제 회사 SSH·Windows/COM/fastboot·BAT/TC·모델·ACON 인수 T-264는 별도다.

2026-11-14 고정 코드·시험 커밋: `475e285cc35765b29470348b581194aa03c47677`. RQ-67/68 구현·문서와 스크립트 정리를 포함한다. 아래 미커밋 표현은 검증 당시 기록이며 현재 적용 기준은 이 커밋이다. [검증·전달 기준](../testing/runs/20261114-agent-monitor-publication.md).


## 2026-11-14 · 플러그인 중심 구현 후속 · RQ-67/D-71

요구사항 독립 리뷰 APPROVED 후 구현했다. 코드 리뷰·최종 회귀는 [이번 실행 기록](../testing/runs/20261114-plugin-centric-implementation.md)을 따른다. 기준 main `e4f53ca1ec288feb3eb1b9ccff8335a398ad321c` 위 미커밋 작업 트리이며 새 고정 제품/시험 커밋은 아직 없다. 아래 과거 커밋·PASS를 새 구현의 근거로 사용하지 않는다.

플러그인 담당자의 읽기 순서는 [요청서](../agents/BSP_UPGRADE_PLUGIN_REQUEST.md) → 이 PORT/회사 COMPANY_MAP·APPLIED → [공개 API·설치 안내](../agents/PLUGIN_CONTROL_API.md) → 관련 코드·시험이다. 확정 방향과 검토 이유는 [설계 마지막 기술 기준](../design/PLUGIN_CENTRIC_INTERFACE_PLAN.md)을 참고한다. Windows 변경은 [PORT-009](PORT-009.md)를 같이 적용한다.

| 변경 영역 | 원본 코드·회사 연결 위치 |
|---|---|
| 전체 화면·서비스 설치 | `apps/agent-monitor/delivery.py`, `manage.py`, `run.sh`; 회사 설치 hook에서 호출. 독립 설치 경로·runtime 유지 |
| 공통 설정·600초 | `core/shared_settings.py`, `core/timeouts.py`, `api/shared_control.py`, `standalone/plugin_client.py`; 회사 ACON/UI는 같은 API 사용 |
| 실패 분석·재실행 | `core/failure_analysis.py`, `manager.py`, `integration.py`, `worker.py`, `api/failure_analysis.py`, `standalone/analysis_worker.py`; 회사 analyzer·신뢰된 verifier를 주입 |
| 브라우저·커넥터 | `packages/gui-test-ui/src/SharedControl.tsx`, `TestPage.tsx`, `host.ts`, connector shared_control/shared_settings_ui/supervisor; 같은 설정·분석 상태 표시 |
| 실행 진입점 정리 | [현재 명령 목록](../../scripts/README.md); 중복 별칭/EXE builder 제거, 회사 호출·CI도 새 경로로 수정 |

전체 전달은 `delivery.py --output <빈 폴더>`로 소스·잠금 의존성·미리 빌드한 Agent Monitor/단독 UI·시험을 함께 복사한다. PluginClient 한 파일 또는 기존 headless GUI wheel만으로 전체 Agent Monitor를 설치하지 않는다. 파일 manifest를 검증하고 회사 backend와 분리된 경로에 설치한다. 회사 모델·ACON 비공개 코드는 포함하지 않는다.

### 데이터·적용·복구

- 기존 documents에 공통 설정과 분석 outbox를 추가한다. DB schema version 변경은 없다. 기존 정책 Run/timeout snapshot·runtime·보드 프로파일·예약을 유지한다.
- 새 Run은 첫 실패 후 분석한다. 신뢰된 조치/종료/보드/입력 검증 전 HOLD이며 같은 원인 재발은 중단한다. BSP 모듈의 입력 변경 재실행은 현재 job/module·계획·소스·운영 게이트를 다시 수락하고 같은 guard에서 기록한다. 회사 호스트는 이 수락 계약을 연결한다.
- 서비스 중지·버전 활성화는 미완료/UNKNOWN·예약을 확인한다. 새 release 설치 실패 시 기존 활성 경로와 runtime을 유지한다. 구버전 Worker로 새 정책 Run을 재개하지 않는다.
- 회사 적용 전 runtime·설정·이미지/TC 사본을 백업하고 동일 버전의 별도 runtime 복원을 검증한다. 실제 회사 이전/복원은 NOT_RUN이다.
- 설치 hook·신뢰된 분석/조치 검증·ACON 연결은 회사 구조에 맞게 연결한다. 공개 Python·OpenSSH·platform-tools 준비는 구현했다. 회사 드라이버·TC 패키지는 제공된 서명/해시·공급 경로로만 설치하며 실제 회사 설치는 별도 검증한다.

T-240~245의 로컬 근거·초기 실패·재시험은 실행 기록에 있다. T-246 실제 회사 Linux/Windows3.13·SSH·플래싱/TC·분석기·ACON 인수는 NOT_RUN이다. 고정 커밋과 최종 전달 manifest는 게시 승인 후 실제 값으로 채우며 회사 APPLIED에는 현지 시험 결과를 남긴다.

아래는 기존 전달 이력이다.

2026-11-12 표시명 후속: Windows Runner의 사용자 표시명을 **TEST BOARD CONNECTOR**로 바꾼다. 참조 PluginClient의 진단 메시지와 서비스 패키지 안내만 변경하며 연결 URL·요청/응답 필드·capability·runner identity·설정 경로는 유지한다. 회사 플러그인의 메뉴/설정에 이전 표시명이 있으면 회사 구조를 확인해 같은 이름으로 맞춘다. 명칭 후속 적용 기준은 [PORT-008](PORT-008.md)과 [명칭 검증 기록](../testing/runs/20261112-board-connector-name.md)이다.

## 2026-11-12 후속 · Runner 설정/배포 안내

[PORT-008 후속](PORT-008.md)의 대상 `55447f87f3241df76a7a110c130252b73b29c941`에서 Windows 설정 탐색/공통 입력 및 integration 패키지의 `INSTALL.md` 안내를 갱신했다. HTTP payload·capability·DB·참조 `PluginClient` 코드는 변경하지 않는다. 원본의 plugin pipeline/service/package 모의 회귀를 포함해 62 PASS다. 실제 회사 플러그인 저장소·다운로드 manifest는 현재 작업 범위에서 접근/검증하지 않았다.

회사 적용 담당자는 전달 Runner의 `src/scripts/setup_flashing.py`, 서비스 패키지 안내와 실제 프로파일을 확인한다. fastboot 모드의 `fastboot init success`를 fast 이전 lkshell 준비 문구로 쓰지 않는다. BAT 후 `**** login : `의 `login :`를 `login_prompt`와 observer `login_markers`에 일치시키고 `root` 로그인은 TC에 둔다. 기존 퓨징 전 `login_steps`·RX splitter/boot/panic 설정은 회사 값으로 유지한다. 실제 lkshell 준비 프롬프트와 TC root 로그인 동작은 미확인이다. 프로파일 변경 후 Runner 정상 재시작과 새 미리 보기가 필요하다. 웹 재빌드만으로 Runner를 재설치하지 않는다.

새 EXE는 생성하지 않고 원본 Git의 기존 EXE ZIP·체크섬을 제거했다. 새 편집형 ZIP도 이번에 생성하지 않았으므로 회사 다운로드 버전/해시 pin을 임의로 바꾸지 않는다. 검증된 후속 배포물을 별도로 만들 때만 실제 pin을 맞춘다. 독립 리뷰 NOT_REVIEWED, 회사 T-209/221 NOT_RUN이며 기존 본문의 고정 전달 이력은 보존한다.

후속 편집 가능한 Runner 배포는 [PORT-008](PORT-008.md)을 참조한다. 아래 고정 커밋과 산출물은 당시 PORT-007 이력으로 유지한다.

2026-11-07 기준 **원본 로컬 구현과 모의 검증을 수행했다. 회사 코드 적용과 실제 환경 인수는 별도이며 T-209는 NOT_RUN이다.** 회사 플러그인의 실제 UI, 설치 hook과 저장소는 이 저장소에서 확인되지 않았고 여기서 구현했다고 주장하지 않는다. 실제 장비·모델 실행 승인은 포함되지 않는다.

## 기준과 전달 상태

- 추적: RQ-60 / D-64 / T-200~209. [연동 설계 §13–14](../design/BSP_UPGRADE_PLUGIN_INTEGRATION.md)에 실제 공개 진입점과 연결 진단을 정리한다. [회사 역할별 안내](../gui_test/BSP_UPGRADE_COMPANY_GUIDE.md)와 [플러그인 요청서](../agents/BSP_UPGRADE_PLUGIN_REQUEST.md)를 함께 전달한다.
- 설계 조사 기준 커밋: `476d95f08169d4a4fbb4a999a94d417d9e59cef3`. 대상 구현 소스·시험 고정 커밋: `1a18ea6fab8b1caead3935ce70cb1e30153d631b` (`feature/bsp-upgrade-gui-test`).
- 이전 로컬 검증 이력: `.local-reports/pvt2/integration/bsp-gui-test-integration.zip` SHA-256 `3fead3852d4e08218a4addbd282d68135fe65332094015f19e036af61beaba11`; `.local-reports/pvt2/wheels/bsp_gui_test-0.1.0-py3-none-any.whl` SHA-256 `6ced451a921c7608da311a9d937ea3bf98a06e13d868f76bbcb2827fed80fd57`. 이 ZIP은 기존 사용자 설정 변경을 포함하므로 최종 전달에서 제외한다. 최종 설치물은 고정 커밋의 깨끗한 작업 트리에서 생성했다. 단일 회사 전달 묶음의 전체 파일과 출처는 동봉 `SHA256SUMS.json`, `source-provenance.json`을 확인한다.
- 선행 기능과 회사 차이는 [PORT-003](PORT-003.md), [PORT-004](PORT-004.md), [PORT-005](PORT-005.md), [PORT-006](PORT-006.md) 및 회사 `COMPANY_MAP.md`·`APPLIED.md`로 확인한다. 과거 PASS를 이번 구현의 PASS로 재사용하지 않는다.

| 최종 설치물 | 크기 (bytes) | SHA-256 |
|---|---:|---|
| `bsp-gui-test-integration.zip` | 403885 | `d0ecdadd76afaba7a73d85a50916e399ea77cfa8984adc97b8761b1611e2ff10` |
| `bsp_gui_test-0.1.0-py3-none-any.whl` | 128055 | `576e349cbbd54d67838e97c55d0ad2e293cc8fad778696cdcf853c60de2bd847` |
| `BSP-Windows-Runner.zip` | 27976854 | `e66fc3b20d379f2cb3f2463a9d23b66a447956ac2de03e621c11de23d253ca4c` |

## 재사용 코드와 회사 연결

원본의 `backend/gui_test/` 코어·API·worker·Windows adapter와 계약 시험을 재사용한다. `standalone/integration.py`는 GUI 전용 상주 호스트이고 `standalone/plugin_client.py`는 서비스 기동·진단, 패턴 기본값, 미리보기·시작·Run 조회용 참조 클라이언트다. 원본 import는 `backend.gui_test`, 설치 wheel은 `gui_test`다. `apps/gui-test/package.py`는 integration 소스 묶음과 headless wheel staging, 선택 UI 포함을 제공한다. Windows Runner는 호환 capability를 가진 별도 설치물로 운영한다. 상세 공개 API와 구성은 연동 설계 §13–14가 원문이다.

회사 담당자는 기존 구조를 비교하고 인증·서비스 계정·설치 hook·API mount·설정 저장소·플러그인 UI를 회사 adapter에서 연결한다. 모듈 패턴 추천 및 편집, 안정적인 멱등 키, Run ID 조회와 진단 표시를 회사 플러그인에서 연결한다. 공통 실행 엔진과 예약·전송·퓨징·재시도·결과 집계를 복제하지 않는다. 회사의 실제 대상 파일과 기존 기능 보존 조건을 `COMPANY_MAP.md`에 기록하고 전체 파일 덮어쓰기를 기본 적용 방법으로 삼지 않는다. 부모 batch 예약 등 연관 변경은 기존 Windows GUI 실행·D-48 경로와 함께 적용하며 endpoint만 부분 반입해 준비 완료로 판단하지 않는다.

회사 환경에서는 허용 installer/TC 루트, 기본 보드·COM, 저장된 TC 명령, Runner identity와 SSH, 승인된 RX 전용 splitter, 보드 fastboot 매핑과 등록 BAT 조건을 확인한다. 비밀정보는 회사 보안 설정으로 관리한다. runtime DB·설정·source-storage/integration-inputs 및 보안 자격 증명 참조의 백업과 동일 버전의 별도 runtime 복원 절차를 회사 환경에 맞게 준비한다. 실제 회사 데이터 이전·복원 검증은 **NOT_RUN**이며 구버전 worker로 새 정책 Run을 재개하지 않는다.

## 검증 근거와 제한

독립 실행 기록은 [2026-11-07 실행 기록](../testing/runs/20261107-bsp-upgrade-integration.md)을 참조한다. 현재 전달받은 로컬 결과는 다음과 같다.

- 집중 검증 169 PASS, 전체 backend 494 PASS. 집중 검증은 전체 실행과 중복되는 부분집합이므로 합산하지 않는다.
- Runner/setup 기본 정책 실행은 131 PASS, 7 SKIP, 5 FAIL로 정책 제한이 있었다. process-only Bypass 재실행은 136 PASS, 7 SKIP이다. 원래 실패를 삭제하거나 기본 정책 PASS로 바꾸지 않는다.
- integration ZIP과 wheel 생성, 설치 import 및 UI build PASS. 전체 Dashboard build도 1,612 modules PASS다. 이는 회사 Linux·Windows 실환경 설치나 장비 인수의 증거가 아니다.
- 고정 커밋의 깨끗한 작업 트리에서 Windows Runner를 빌드했고 portable smoke는 10 PASS (`.local-reports/pvt2/portable-runner-smoke.log`)다. T-208의 실제 Linux 설치·복원은 NOT_RUN이다.
- Sol High 독립 코드 리뷰 APPROVED: `.local-reports/rq60-code-review`. 실제 시험 명령과 환경, 개별 ID 판정 및 미검증 범위는 실행 기록에서 확인한다. T-209 회사 Linux/SSH/Windows/장비/TC/splitter 인수는 NOT_RUN이다.

## 회사 적용과 사용 순서

1. 회사 필수 지침, 이 PORT, `COMPANY_MAP.md`·`APPLIED.md`, 관련 코드와 시험 및 필요한 상세 설계를 순서대로 확인한다. 고정 구현 커밋과 최종 설치물·체크섬을 전달받아 검증한다.
2. 회사 백엔드 담당자는 공통 코드·계약을 재사용하고 회사 서비스·인증 접점을 연결한다. 플러그인 담당자는 회사 UI·설정·설치 hook과 참조 클라이언트를 연결한다. 별도 상주 Windows Runner와 Linux 서비스의 수명을 플러그인 요청에 종속시키지 않는다.
3. 회사 환경 사실과 비밀 저장소를 설정하고 플러그인 연결 진단을 확인한 다음 모의 인수와 영향 회귀를 수행한다. 상세 절차는 [회사 역할별 안내](../gui_test/BSP_UPGRADE_COMPANY_GUIDE.md)를 따른다. 실제 장비 시험은 별도 승인 범위에서 실행한다.
4. 일상 사용자는 플러그인에서 완료된 BAT 경로와 모듈을 선택하고 제안 패턴을 필요에 따라 미리보고 수정한다. 같은 실행 의도의 재접속에는 같은 키와 Run ID를 사용한다. UNKNOWN 장비 상태는 물리 확인과 정해진 조정 절차를 따른다.
5. 회사 적용 커밋·범위·시험 결과·잔여 제약을 `APPLIED.md`에 기록한다. 회사 인수, 데이터 복원 및 최종 전달물의 상태는 실제 증거가 생겼을 때 각각 갱신한다.

## 2026-11-13 연결 토큰 제거 후속

현재 소스의 Runner·등록·플러그인 연결에는 사용자 토큰 설정이 필요 없다. 이전 고정 커밋의 동작은 당시 기록을 따른다. 함께 갱신할 파일·회사 접점·복원·검증은 [PORT-009 후속](PORT-009.md#2026-11-13-연결-토큰-제거-후속--rq-64--d-68)을 따른다. 새 배포 EXE/ZIP은 만들지 않는다.

2026-11-14 RQ-68 후속: standalone/analysis_runtime.py와 Worker 연결, ModuleSelectionPort.validate_retry/retry_guard, core/retention.py 및 API, apps/agent-monitor의 prerequisites/recovery를 함께 복사한다. 현재 job/module 재수락·기존 저장 데이터·운영 게이트를 유지한다. 분석/검증기는 회사 명령과 증거 수집 접점만 조정한다. 공개 명령·선행 조건·설정 저장·복구는 [PLUGIN_CONTROL_API](../agents/PLUGIN_CONTROL_API.md), 변경 기준/시험과 남은 실제 인수는 [실행 기록](../testing/runs/20261114-remaining-implementation.md)을 따른다. 미커밋 변경이므로 배포 전 검증 manifest와 고정 커밋을 기록한다.

## 2026-11-18 · 플러그인 모듈 후보와 자동 사전 검사

모듈 후보 게시·선택 콤보박스, Jira 화면 정리와 별도 Preflight 버튼 제거는 [PORT-012](PORT-012.md)을 적용한다. full-host client와 회사 영속 모듈 callback 매핑이 필요하며 기존 모듈/config/job·실행 소유권을 보존한다. 이번 변경은 미커밋으로 새 게시 pin이 없고 실제 회사 인수는 NOT_RUN이다.
