# PORT-009 · 보드 커넥터 GUI와 공통 연결/콘솔

## RQ-69 · 최초 설정·전체 흐름 보완

기준 `5775661ddcf7b6f9020fdc9ee058b2a12098f819` 대비 이번 후속의 코드·시험 고정 커밋은 `bfb7a21075d2bc7f44f414e087179720cdd3dd5c`다. 과거 고정 커밋만 적용하면 아래 보완은 포함되지 않는다. [공개 연결/설정 절차](../agents/PLUGIN_CONTROL_API.md), [독립 리뷰](../testing/runs/20261114-plugin-flow-audit.md), [현재 시험](../testing/runs/20261114-plugin-flow-implementation.md)을 함께 적용한다.

- 초기 접속: `core/connector_bootstrap.py`, `connector/bootstrap.py`, 기존 CMD/Python launcher·supervisor·shared_control. 회사가 보유한 Windows에서 접근 가능한 Linux 주소/계정/포트를 export/import에 연결한다. SSH 자격은 로컬 보존한다.
- 실행 프로파일: `core/api integration_profiles.py`, `shared_settings.py`, `Manager.save_document` CAS, Windows Settings/Host/적용 receipt를 함께 반영한다. 프로파일 patch·실제 적용 해시를 생략하지 않는다.
- 공통 요청: `PluginClient`, 양 호스트 middleware의 요청별 identity 확인·단독 화면 권한, `api/router.py` 삭제 경로, `RegisteredWindows` freshness gate와 console receipt CAS를 함께 적용한다.
- 분석/BSP: `analysis_runtime.context`의 제한된 플래싱 근거, `BspPluginClient`와 전체 호스트의 명시 scope를 재사용한다. Engine·Worker/보고 계약을 복제하지 않는다.

새 DB 테이블 이전은 없다. 기존 documents와 Windows JSON에 추가 데이터를 저장한다. 기존 설정/로그/실패/UNKNOWN을 보존하고 bootstrap 저장은 backup을 만든다. 롤백은 안전 종료·동일 runtime 보존 후 코드/설정 백업을 함께 복구한다. 구버전에는 새 프로파일·bootstrap 지원이 없으므로 운영 중 즉시 교체하지 않는다. 실제 회사 SSH·Windows/COM/fastboot·BAT/TC·모델·ACON 인수 T-264는 별도다.

최신 커넥터 후속 코드·시험 커밋: `5ca4d8df925fbb329048322f4e7635b575265110`. 미리보기 기동·간략 화면·연결 전원 버튼·상태 tooltip과 T-257/258을 포함한다. 현재 파일 기준 web36 PASS/Chromium14 PASS. [게시 전 검증](../testing/runs/20261114-connector-compact-ui.md#게시-전-현재-파일-재검증). 아래 미커밋 표시는 당시 작업 이력이다.


2026-11-14 고정 코드·시험 커밋: `475e285cc35765b29470348b581194aa03c47677`. RQ-67/68 구현·문서와 스크립트 정리를 포함한다. 아래 미커밋 표현은 검증 당시 기록이며 현재 적용 기준은 이 커밋이다. [검증·전달 기준](../testing/runs/20261114-agent-monitor-publication.md).


## 2026-11-14 · 설정 탭·스냅샷 정책·자동 준비 후속

기준은 `e4f53ca1ec288feb3eb1b9ccff8335a398ad321c`이며 이 후속은 미커밋 변경이다. 새 고정 제품 커밋·배포 ZIP은 아직 없다. 기존 웹 GUI 적용분 위에 아래 접점을 함께 반영하고 회사 적용 커밋을 `COMPANY_MAP.md`/`APPLIED.md`에 기록한다.

| 변경 | 재사용·연결 위치 | 회사 적용 조건 |
|---|---|---|
| 환경설정의 보드별 탭·공통 설정·저장 공간 | `packages/gui-test-ui/src/connector_web/view.mjs`, `style.css`, `connector/web_assets/host.mjs`, `web_actions.py` | 회사 호스트의 기존 선택·초안·CSRF·읽기 전용 범위를 유지한다. UI만 복사하지 않고 host callback을 연결한다 |
| Qt 호환 저장 공간 패널 | `connector/shared_settings_ui.py`, `gui.py`, `supervisor.py`, `preview.py` | 기본 브라우저와 같은 중앙 정책 API를 사용한다. 보관 시간·GiB·저장·예상 정리를 제공한다 |
| 자동 스냅샷 정리 | `core/retention.py`, `execution/retention.py`, `api/storage.py`, `core/worker.py`, `execution/host.py` | 기본 ON/7일/20 GiB, 보호 참조·실패 근거·업로드 유예·dry-run을 유지한다. 일부 경로 제외와 목표 용량 초과를 숨기지 않는다 |
| 생산·참조 수락 잠금 | `SourceService.apply`, `Manager.start`, `FailureAnalysis.submit`, `IntegrationService.preview/start/prepare_one/prepare_run`, Host snapshot publication | 정리 모듈만 먼저 활성화하지 않는다. 생산자와 수락 처리의 같은 잠금까지 한 단위로 적용한다 |
| 플러그인·설정 파일 | `standalone/plugin_client.py`의 storage 메서드, `core.retention` export/apply CLI | revision CAS·fresh runner identity·적용 대기 상태를 보존한다. 회사의 물리 DB 경로와 중앙 principal 연결만 조정한다 |
| 최초 공개 도구·의존성 준비 | [스크립트 목록](../../scripts/README.md), `bootstrap-prerequisites.sh/.ps1`, Agent Monitor 관리 진입 | 회사 프록시·패키지 미러·관리자 권한 정책을 먼저 확인한다. 이미 설치된 도구와 실행 중 runtime은 보존한다 |

정책·최근 정리 보고는 기존 GUI `documents`와 Windows `runner_meta`에 추가된다. 별도 스키마 이전은 없다. **정리로 이미 제거한 성공 캐시는 코드 rollback만으로 복원되지 않는다.** 원본 TC/이미지에서 다시 준비하며 활성·실패 기록은 보존한다. 기존 runtime 전체의 백업·동일 버전 복구 절차를 유지한다.

[사용 가이드](../gui_test/TEST_BOARD_CONNECTOR_GUI.md#스냅샷-저장-공간), [공통 API 안내](../agents/PLUGIN_CONTROL_API.md), [이번 실행 기록](../testing/runs/20261114-remaining-implementation.md)을 함께 전달한다. 최종 통합 회귀 1009 PASS/24 SKIP, Chromium13+6 PASS와 두 UI 빌드는 임시 경로·모의 연결 근거다. [독립 리뷰 판정](../testing/runs/20261114-remaining-code-review.md)을 함께 확인하며 회사 Windows·실제 설치·장비 인수는 NOT_RUN이다. 사용자 runtime의 실제 정리는 실행하지 않았다.

## 2026-11-14 · 웹 기본 화면과 CMD 오류 진단

사용자 승인 범위는 **CMD 기본 실행 → Windows 실행부 준비/재사용 → 웹 화면 열기**다. Qt는 `--ui qt` 호환 옵션이다. 적용은 미커밋 변경이며 새 고정 커밋·배포 ZIP은 아직 없다. 아래 과거 고정 커밋만 적용하면 이번 웹 전환이 포함되지 않는다. [사용·오류 해결 가이드](../gui_test/TEST_BOARD_CONNECTOR_GUI.md), [개선 설계](../design/BOARD_CONNECTOR_WEB_GUI_PLAN.md), [시험/소스 manifest](../testing/runs/20261114-connector-web.md), [실제 Astra 리뷰 상태](../testing/runs/20261114-connector-web-review.md)를 함께 전달한다.

| 적용 파일/접점 | 회사 반영·보존 조건 |
|---|---|
| `board-connector.cmd`, `scripts/board_connector.py` | BC 단계 로그/명시 Python/무실행 진단, browser 기본 core lock 준비. 회사 소스 전체 위치/로컬 home·pip 설정 보존 |
| `connector/__main__.py`, `supervisor.py`의 browser hook·제어 잠금·Client 오류 보존 | 같은 Manager/Host 재사용. 실행 중 구버전 Manager를 강제 교체하거나 새 Worker를 만들지 않음 |
| `connector/web.py`, `web_actions.py`, `native_picker.py`, `web_assets/index.html`, `host.mjs` | 브라우저 세션/CSRF/instance/Host 제한 유지. 표준 picker는 Windows 소유 프로세스에서 실행. 로그 열기는 고정 home/logs만 허용 |
| `packages/gui-test-ui/src/connector_web/view.mjs`, `style.css` | API·인증·폴링 없는 재사용 뷰. 회사 호스트는 명시된 host 콜백을 연결하고 같은 상태·제어권을 표시 |
| `apps/gui-test/package.py`, `pyproject.toml`, `scripts/build_connector_bundle.py` 자산 접점 | 원본 없는 배포에서도 고정 자산 4개를 함께 포함. npm/CDN 런타임 의존성 추가 없음. 실제 새 Windows ZIP 생성/실행 완료로 확대하지 않음 |
| launcher/web API 시험, `connector-web.spec.ts`, 모의 fixture/실행 스크립트 | T-247~249 및 기존 T-232~239 회귀를 재사용. fixture는 회사 서비스에 실행하지 않음 |

선행 기능은 RQ-63~67의 회사 적용 상태를 확인한다. 공통 설정 변경 중인 회사 접점은 `shared_control`을 그대로 재사용한다. DB 이전·영속 설정 포맷 변경·공유 연결 토큰 입력은 없다. 브라우저 세션은 자동 생성되는 별도 로컬 제어 자격이다. 기존 home/DB/TC Python/Qt 환경·로그·UNKNOWN 실행을 보존한다. 복원은 작업 안전 종료 후 이 변경의 코드/진입점만 이전 버전으로 복구하고 사용자 데이터는 삭제하지 않는다.

로컬 모의/API/패키징/Chromium 통과와 실제 Windows 회사 인수 T-250은 구분한다. 설계와 웹 GUI 변경 범위는 Astra xhigh APPROVED이며 최초 CHANGES_REQUESTED 네 건을 수정했다. 최신 통합 관련 회귀 241 PASS/Windows 20 SKIP, Chromium 12 PASS, 앞선 검토자 독립 web 단위 34 PASS다. 후속 보드/로그 탭의 다중 COM 오류·ARIA 두 P2 코드/시험 delta도 별도 승인받았다. storage 실제 정리·BC-29 공개 도구 설치는 그 승인 범위가 아니다. 실제 Windows/회사 배포 가능 판정은 아직 아니다. CMD 원인과 Z: 실행 성공 여부, 별도 public-tools 실제 설치는 회사에서 확인한다.

## 2026-11-14 · 공통 설정 편집·플러그인 분석 · RQ-67/D-71

현재 소스에 공통 설정 편집·서버 경로 선택·설정 적용 응답·분석 상태를 추가했다. 기준 main `e4f53ca1ec288feb3eb1b9ccff8335a398ad321c` 위 미커밋 작업 트리이며 새 고정 커밋은 없다. [PORT-007](PORT-007.md), [공개 연동 안내](../agents/PLUGIN_CONTROL_API.md), [검증 기록](../testing/runs/20261114-plugin-centric-implementation.md)을 함께 따른다.

| 변경 위치 | 적용 내용·보존 조건 |
|---|---|
| connector/shared_control.py | 공통 서버 요청·desired 보관·실행/시작 잠금 안의 안전 적용·Host 시작 설정 해시와 실제 APPLIED 확인 |
| connector/shared_settings_ui.py, gui.py | 공통 경로/패턴/플래싱 프로파일/timeout 편집·Linux 경로 선택·비동기 미저장 입력 보존·분석 상태 |
| connector/supervisor.py | 기존 연결·IPC에 공통 설정/경로·상태 요청 연결. 별도 실행 관리자 없음 |
| execution/host.py | 실제 프로세스가 읽은 설정 필드 해시를 inventory에 보고. 실행 중 disk 변경을 적용 성공으로 오인하지 않음 |
| core/shared_settings.py, api/shared_control.py | 중앙 CAS와 대상 runner의 desired/receipt. 공유 토큰 추가 없음 |

Windows 로컬 설정·SSH 자격과 중앙 Linux 경로를 구분한다. Windows 장비 요청은 중앙 저장 후 PENDING이며 작업/예약/UNKNOWN이 없는 연결 재시작에서만 적용한다. 다른 runner·오래된 revision·새 Host 확인 없는 저장은 APPLIED가 아니다. 연결 중 단순 polling은 미저장 입력을 덮어쓰지 않는다.

기존 Python 3.13·Qt 고정 버전·시리얼 코어를 재사용하고 새 의존성은 없다. `board-connector.cmd`를 유지하며 이름을 바꾼 빌드/진단 명령은 [스크립트 목록](../../scripts/README.md)을 따른다. 새 EXE는 만들지 않는다. runtime·프로파일·실패/UNKNOWN 이력과 실행 중 환경을 보존한다. 복구 시 동일 버전과 별도 runtime을 사용하며 중앙 desired 변경은 오래된 파일로 덮어쓰지 말고 최신 revision으로 요청한다.

T-243 Qt/browser와 T-244 복사 소스의 로컬 근거는 실행 기록에 있다. 새 Windows 실행/회사 SSH·장비·분석 모델·ACON 인수 T-246은 NOT_RUN이다.

아래 고정 구현과 검증은 기존 기능의 전달 이력이다.

상태: 로컬 소스 구현·모의 검증, 회사 T-228 NOT_RUN. RQ-63/D-67/T-222~228/REG-0079. [설치·사용·연동 가이드](../gui_test/TEST_BOARD_CONNECTOR_GUI.md), [계약](../design/BOARD_CONNECTOR_CONTRACT.md), [실행 기록](../testing/runs/20261112-board-connector-gui.md).

기준 고정 커밋 `6734c843c46e986ce5c35a0851c38ac009661b98`; 제품·시험 대상 고정 커밋은 `ed3d2ac409ce586c0682637fba4c6f1989247e28`다. 후속 문서 커밋은 이 제품 대상을 변경하지 않는다. source SHA manifest는 게시 전 로컬 증거이며 현재 전달 비교에는 위 고정 커밋을 사용한다. 새 배포 ZIP은 없고 실제 회사 인수 전 운영 적용 완료로 취급하지 않는다. 기존 PORT-004/007/008과 timeout/영구 삭제 WIP를 함께 비교하고 회사 필수 정책·COMPANY_MAP/APPLIED를 먼저 확인한다.

## 파일과 회사 연결

- 재사용 Python: `backend/gui_test/connector/`(registry/console/settings/supervisor/gui/preview/logs/workers/api), 기존 execution Host/FlashService/batches/launch·WindowsRemote·core Manager/IntegrationService 접점.
- 재사용 UI: `packages/gui-test-ui/src/ConnectorStatus.tsx`, TestPage·test.css. capability opt-in이고 호스트 CSS --gt-*를 사용한다. 서버/TC catalog 없이 inventory부터 표시한다.
- 전체 호스트: backend/api/main.py의 pairing/기존 plugin auth·health adapter, backend/worker/main.py의 물리 DB별 단일 DashboardWorkers. standalone Worker를 회사 서버에 추가 기동하지 않는다.
- 참조 plugin: standalone/plugin_client.py의 inventory/board_console/connector_errors. 읽기 discovery와 기존 strict 실행 preparation을 구분한다. 회사 plugin 원본은 없으므로 현지 adapter가 이 계약을 소비해야 한다.
- 소스 진입: `python -m backend.gui_test.connector`, `board-connector.cmd`, 고정 Qt requirements.lock. 앱 pyproject에 connector package/desktop optional dependency/entrypoint 포함. 기존 editable builder의 새 Qt wheel 조립은 이 변경에서 실행하지 않았다.

RQ-64/D-68 후속에서는 Runner·등록·플러그인 연결 토큰을 설정하지 않는다. 제어 IPC 자격은 관리자가 자동 생성한다. endpoint는 loopback SSH reverse identity 왕복 확인 후 등록한다. 회사 8765는 기존 서비스를 가리키는 저장값이며 공통 기본 포트를 바꾸지 않는다. runner URL/COM은 회사 plugin에 복제하지 않는다.

공통 서버 TC 선택을 재사용한다. 새 `runner: registered` 모드는 선택적인 기존 windows-http URL fallback을 없앤다. integration의 누락 connection/runner ID/TC root는 공통 registry/source에서 읽되 기존 명시 설정과 Run snapshot을 우선한다. snapshot 전송이므로 Windows source_root는 새 설정에서 필수가 아니다. Z:/UNC 가변 직접 실행·임의 원격 파일 탐색은 미구현이다. 스냅샷 자동 정리는 위 2026-11-14 후속을 적용한다.

## 데이터 이전·복원

기존 runtime/JSON/DB를 백업 후 보존한다. 새 registry DB는 additive sidecar다. 기존 source_root/플래시/추가 필드는 원자 저장·이름 있는 백업으로 보존한다. GUI에서 줄인 보드는 비활성 설정으로 보관하며 실행 기록은 지우지 않는다. 다른 runner identity는 자동 교체/이관하지 않는다. 복원은 안전 종료 후 이전 코드·프로파일과 새 registry DB를 함께 보존하는 방식이다. UNKNOWN/예약/삭제 진행을 숨기는 DB 삭제를 하지 않는다.

## 검증과 남은 인수

실행 명령/현재 결과는 위 실행 기록을 따른다. fake HTTP/serial/process·Qt offscreen·브라우저 fixture는 실제 Windows/회사 plugin 수신 근거가 아니다. 회사는 Qt 6.8.3 Windows wheel/오프라인 라이선스·무결성, OpenSSH key/agent·회사 포트, loopback reverse identity, 실제 RX splitter 분리와 보드별 수집·batch handoff, 창 닫기 후 시험 지속, 중앙 오류 cursor 재조회, 안전 종료/재접속을 검증한다. 기존 timeout/영구 삭제와 API request/catalog timeout을 분리해 회귀한다. 새 EXE/전달 ZIP은 생성하지 않았다. 사용자 지시로 위 제품 커밋과 이식 기록을 게시한다.

## 사용자 안내 전달

회사 전달 시 [보드 커넥터 가이드](../gui_test/TEST_BOARD_CONNECTOR_GUI.md)를 함께 제공한다. 단일 실행 명령, Windows–Linux 연결도, 최초 서버 설정, 사용 순서, 예외 조치를 포함한다. 회사 소스 경로·서비스 포트·SSH 설정을 현지 값으로 맞춘다. 서비스 연결 토큰은 필요 없다.

## 2026-11-12 CI 복구 후속

기준 6cf5552 위의 REG-0080 수정은 이 절을 추가한 로컬 커밋과 [실행 기록](../testing/runs/20261112-ci-refresh.md)의 diff hash로 식별한다. POSIX builder 잠금·connector exporter와 시험 계약/Qt CI 의존성을 함께 검토한다. 기존 Windows byte 잠금·설정/프로토콜은 유지하며 migration과 승인 산출물 교체는 없다. 회사 구조에 맞춰 관련 파일/시험만 적용하고 기존 코드 rollback은 이 수정만 역변경한다. 실제 Windows·회사 인수 및 설치형 desktop connector의 호스트 스크립트 참조는 별도 검증 대상이다.

## 경로 표시 후속 · 고정 커밋

2026-11-13 경로 표시 대상은 `9fa5a0f88a8b26d333be3906cf3d63fa767d570d`다. 원격 CI 복구 기준 `e0053bfc101f864cbb00297ae9fd4f438288dad1` 위에 적용했고 기존 GUI 고정 대상 이후의 변경을 포함한다. connector `paths.py`/API/supervisor/GUI/preview와 Host·FlashService의 job 경로 기록을 함께 반영한다. 등록 응답 `server_paths` 및 최근 실행 응답 `execution_paths`는 선택 필드이며 구버전 수신 시 미수신으로 표시한다. 기존 DB의 JSON 필드만 추가하고 실행 입력·경로 변환·플래싱 버튼은 추가하지 않는다. [후속 검증](../testing/runs/20261113-board-connector-paths.md)을 확인한다.

## 2026-11-13 연결 토큰 제거 후속 · RQ-64 / D-68

원본 기준은 `48a34237939dd31f62c8b3b83ef13d55324009e2`다. 후속 제품·시험 고정 적용 커밋은 `929158f672a5a155d00b89ca679cf775ea3744b3`다. 아래 범위를 함께 적용하고 회사 대상 파일·적용 커밋을 COMPANY_MAP/APPLIED에 기록한다.

- 서버: `backend/api/main.py`, `backend/gui_test/standalone/integration.py`, `connector/api.py`, `connector/registry.py`, `runtime.py`, `api/router.py`.
- Windows·공통 클라이언트: `execution/host.py`, `execution/bundle.py`, `adapters/windows_remote.py`, `connector/supervisor.py`, `standalone/plugin_client.py`.
- 설정·기존 BSP 연결: `scripts/setup_runtime.py`, `scripts/setup_flashing.py`, `backend/worker/hardware.py`; 패키지 안내 `apps/gui-test/package.py`.
- 회사 플러그인은 `PluginClient(url, expected_identity=identity)`를 사용한다. HTTP 직접 호출 시 loopback URL과 `X-Bsp-Service: plugin`을 사용한다. 이 헤더는 비밀이 아니다. 보드 identity·Run ID·멱등 키 처리는 유지한다.

기존 세 서비스 토큰 환경변수/파일은 읽거나 전송하지 않는다. SSH 키·사용자 경로·DB·실행 기록은 보존한다. 관리자 IPC 자격은 자동 관리하므로 삭제하지 않는다. DB 이전과 새 의존성은 없다. 기존 작업을 정상 종료한 뒤 API/Worker·커넥터·플러그인 클라이언트를 함께 갱신한다. 복원 시 세 요소의 기존 소스와 기존 설정을 함께 복원한다. 이전 버전 서버와 혼용하면 이전 토큰 요구가 남을 수 있다.

시험은 T-230, 실제 회사 Windows/SSH/장비 인수는 T-231이다. [실행 기록](../testing/runs/20261113-tokenless-connections.md)에서 로컬 결과와 환경 제약을 확인한다. 회사 플러그인 UI 원본은 이 저장소에 없어 실제 적용은 확인하지 않았다.

## 단일 설치·실행 진입점 · RQ-65 / D-69

기준 `683447734f3d47feb85ddf472b051663706f862e`, 제품·시험 고정 대상은 `46a0cb9328f3cb351078b2d2b8e48faf0aaa2fc5`, main 병합은 `ad16eaac5c6837b85e73aea52864ce9b101170f1`다. `board-connector.cmd`와 `scripts/board_connector.py`, 두 기존 requirements.lock을 같은 소스 배치에 포함한다. 제거 대상은 `apps/board-connector/launch.cmd`, `scripts/start-windows-runner.ps1`, `scripts/connect-windows.ps1`이다. 회사 바로가기/안내가 이전 파일을 호출하면 새 CMD로 연결한다. 기존 CLI·Linux/웹 서비스·빌드 스크립트는 별도 역할을 유지한다.

Python 3.13 64비트(3.11/3.12 호환), OpenSSH, 회사 pip 네트워크/오프라인 설정이 선행 조건이다. 새 Python 의존성·DB 이전은 없다. 기존 home·TC Python·보드/SSH 설정을 유지하며, 완성된 기존 `.venv`를 읽기 전용 재사용하거나 home/connector-environments에 새 환경을 준비한다. 설치 잠금·검증 후 환경 선택 파일을 원자 교체하며 실패한 신규 환경만 정리한다. 기존 환경은 실행 중일 수 있어 자동 삭제하지 않는다. 소스/TC/이미지를 설치 캐시에 복사하지 않는다.

복원은 연결·시험 종료 후 기존 소스/바로가기를 복구하며 사용자 home·DB를 삭제하지 않는다. 시험과 실제 Windows/회사 범위는 [실행 기록](../testing/runs/20261113-connector-launcher.md)의 T-232~234를 따른다.

## Python 3.13 후속

기준 `91d658f1461ec017952dad37bcabb3f149703da8` 이후 RQ-65/D-69/T-235/REG-0083 변경이다. `board-connector.cmd`, `scripts/board_connector.py`, `tests/test_board_connector_launcher.py`, Windows 회귀 workflow를 함께 적용한다. Python 3.13 64비트가 우선이며 3.11/3.12도 호환된다. 기존 Qt 핀은 3.13을 지원하므로 새 패키지는 추가하지 않는다. 다른 minor의 환경은 새로 준비하고 기존 설정/환경은 보존한다. 데이터 이전은 없고 복원 시 이전 코드·기존 환경을 재사용한다. [검증 기록](../testing/runs/20261113-connector-python313.md). 고정 제품·시험 커밋 `1447c207515f828dcf925075625b6f0f7c3a6d60`, main 병합 `4c7b18ae6f21dcfb9981b4ce61e338a25d48b1f6`. Windows Python 3.13.17 CI 644 PASS/4 SKIP와 실제 최초 설치·오프라인 재사용 PASS. 회사 Z: 경로 문제와 실제 GUI·SSH·장비 인수는 별도다.

## 포트 멀티플렉서 후속

RQ-66/D-70/T-236~239/REG-0084. 기준 `77708ad40c4b869b084121597643948cb923ad70`; 고정 제품·시험 커밋 `dc2f855cf7e24638763bea7c2696673d4d407a02`, main 병합 `e963c966b0c37f9e1d5ac8f6b8fdb1e0326f5980`. Python 3.13·기존 pySerial 3.5·Qt 6.8.3을 사용하며 새 의존성·DB 이전은 없다. `connector/multiplexer.py`, `serial_proxy.py`, `console.py`, `settings.py`, `supervisor.py`, `gui.py`, `preview.py`와 `execution/host.py`, `flashing.py`, 관련 시험을 함께 적용한다.

회사 공통 통신 모듈에서 Serial import/생성 부분 한 곳을 [가이드](../gui_test/TEST_BOARD_CONNECTOR_GUI.md#tc-공통-모듈-연결)에 맞춘다. TC별 COM 인자를 바꾸지 않는다. 어댑터·실행 lease·loopback 포트는 Host가 자동 제공한다. 새로운 프로파일만 proxy 기본이며 기존 설정은 연결 종료 후 명시 전환한다. 기존 windows-runner.json·native/RX 설정은 백업·보존한다. 복원은 연결/작업 안전 종료 후 이전 코드·설정으로 되돌리며 Run/오류 DB를 삭제하지 않는다.

사용자 토큰 설정·가상 COM 드라이버·별도 멀티플렉서 앱은 필요 없다. PuTTY는 별도 설치 프로그램이며 PATH/표준 위치 검색 또는 파일 선택을 사용한다. 실제 회사 공통 모듈·UART 드라이버·제어선·SSH·plugin 인수 T-239는 NOT_RUN이다. ADB 서버 프록시는 미구현 별도 경로다. [검증 기록](../testing/runs/20261113-connector-multiplexer.md).

제품 `dc2f855cf7e24638763bea7c2696673d4d407a02`을 PR #22로 main `e963c966b0c37f9e1d5ac8f6b8fdb1e0326f5980`에 병합했다. Windows Python 3.13 회귀 655 PASS/4 SKIP, 최초 설치·오프라인 재실행 PASS. Linux Python 1462 PASS/21 SKIP, 대시보드 브라우저 60 PASS와 standalone 브라우저 18 PASS. Windows 3.12 독립 빌드·오프라인 설치·실행은 PowerShell/pwsh 모두 PASS. 회사 UART·TC·SSH/PuTTY T-239는 NOT_RUN이다.


## 실제 로컬 미리보기 기동 후속 · 미커밋

기준 b685ab9 위에서 connector/web.py의 preview 포트0 호출을 유효8774+fallback으로 수정했다. 테스트/REG-0090·가이드·[기동 기록](../testing/runs/20261114-connector-preview.md)을 함께 적용한다. Windows production 포트/Manager/COM 계약과 DB는 바꾸지 않는다. web36 PASS와 Mac 실제 Chrome 모의 연결을 확인했으며 이번 후속 수정은 아직 원격 고정 커밋에 포함되지 않는다.


## 보드 리스트·상태등·접이식 로그 후속 · 미커밋

기준 b685ab9와 로컬 preview 수정 이후의 UI 변경이다. `packages/gui-test-ui/src/connector_web/view.mjs`, `style.css`와 `tests/e2e/connector-web.spec.ts`를 함께 적용한다. 신호등은 실제 수신 상태를 사용하고 stale 정상값은 확인 필요로 바꾼다. 멀티플렉서 안내·작은 로그는 접기/열기를 제공하며 TC 로그는 프로그램 stdout/stderr, 보드 콘솔은 UART 수신, PuTTY는 별도 터미널로 구분한다. 새 의존성·DB 이전·COM/실행 계약 변경은 없다. 복원은 연결/작업 안전 종료 후 이전 UI 자산으로 되돌리며 설정/기록은 유지한다. Chromium14/web36 PASS와 Mac 모의 화면 확인은 [T-258 기록](../testing/runs/20261114-connector-compact-ui.md)을 따른다. 회사 Windows·UART·SSH·PuTTY는 별도 인수이며 이 수정은 아직 원격 고정 커밋에 포함되지 않는다.


### 상태 설명·전원 버튼·패널 정렬 후속

같은 미커밋 UI 자산·브라우저 시험에서 작은 단계 설명, 단일 연결 전원 버튼, 목록/상세 높이 정렬을 추가했다. 사용자 최신 지시로 로그는 항상 보이며 접지 않는다. 기존 안전 종료 API와 저장 데이터는 유지한다. 적용 파일·복원·선행 조건은 위 UI 후속과 같다. 검증은 [T-259](../testing/runs/20261114-connector-status-help.md)를 따르며 회사 실제 인수와 구분한다.

배치 후속(기준 `5775661` 위 미커밋): 동일 view/CSS에서 영문 제목만 남기고 상세 순서를 로그 → 소스/실행 경로 → 연결 상세/콘솔 안내로 조정했다. 실행·DB/API·의존성 변경은 없다. [T-259 배치 재검증](../testing/runs/20261114-connector-status-help.md#배치제목-후속)을 함께 확인한다.
