# PORT-009 · 보드 커넥터 GUI와 공통 연결/콘솔

상태: 로컬 소스 구현·모의 검증, 회사 T-228 NOT_RUN. RQ-63/D-67/T-222~228/REG-0079. [설치·사용·연동 가이드](../gui_test/TEST_BOARD_CONNECTOR_GUI.md), [계약](../design/BOARD_CONNECTOR_CONTRACT.md), [실행 기록](../testing/runs/20261112-board-connector-gui.md).

기준 고정 커밋 `6734c843c46e986ce5c35a0851c38ac009661b98`; 제품·시험 대상 고정 커밋은 `ed3d2ac409ce586c0682637fba4c6f1989247e28`다. 후속 문서 커밋은 이 제품 대상을 변경하지 않는다. source SHA manifest는 게시 전 로컬 증거이며 현재 전달 비교에는 위 고정 커밋을 사용한다. 새 배포 ZIP은 없고 실제 회사 인수 전 운영 적용 완료로 취급하지 않는다. 기존 PORT-004/007/008과 timeout/영구 삭제 WIP를 함께 비교하고 회사 필수 정책·COMPANY_MAP/APPLIED를 먼저 확인한다.

## 파일과 회사 연결

- 재사용 Python: `backend/gui_test/connector/`(registry/console/settings/supervisor/gui/preview/logs/workers/api), 기존 execution Host/FlashService/batches/launch·WindowsRemote·core Manager/IntegrationService 접점.
- 재사용 UI: `packages/gui-test-ui/src/ConnectorStatus.tsx`, TestPage·test.css. capability opt-in이고 호스트 CSS --gt-*를 사용한다. 서버/TC catalog 없이 inventory부터 표시한다.
- 전체 호스트: backend/api/main.py의 pairing/기존 plugin auth·health adapter, backend/worker/main.py의 물리 DB별 단일 DashboardWorkers. standalone Worker를 회사 서버에 추가 기동하지 않는다.
- 참조 plugin: standalone/plugin_client.py의 inventory/board_console/connector_errors. 읽기 discovery와 기존 strict 실행 preparation을 구분한다. 회사 plugin 원본은 없으므로 현지 adapter가 이 계약을 소비해야 한다.
- 소스 진입: `python -m backend.gui_test.connector`, `board-connector.cmd`, 고정 Qt requirements.lock. 앱 pyproject에 connector package/desktop optional dependency/entrypoint 포함. 기존 editable builder의 새 Qt wheel 조립은 이 변경에서 실행하지 않았다.

RQ-64/D-68 후속에서는 Runner·등록·플러그인 연결 토큰을 설정하지 않는다. 제어 IPC 자격은 관리자가 자동 생성한다. endpoint는 loopback SSH reverse identity 왕복 확인 후 등록한다. 회사 8765는 기존 서비스를 가리키는 저장값이며 공통 기본 포트를 바꾸지 않는다. runner URL/COM은 회사 plugin에 복제하지 않는다.

공통 서버 TC 선택을 재사용한다. 새 `runner: registered` 모드는 선택적인 기존 windows-http URL fallback을 없앤다. integration의 누락 connection/runner ID/TC root는 공통 registry/source에서 읽되 기존 명시 설정과 Run snapshot을 우선한다. snapshot 전송이므로 Windows source_root는 새 설정에서 필수가 아니다. Z:/UNC 가변 직접 실행·새 GC·임의 원격 파일 탐색은 미구현이다.

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

기준 `91d658f1461ec017952dad37bcabb3f149703da8` 이후 RQ-65/D-69/T-235/REG-0083 변경이다. `board-connector.cmd`, `scripts/board_connector.py`, `tests/test_board_connector_launcher.py`, Windows 회귀 workflow를 함께 적용한다. Python 3.13 64비트가 우선이며 3.11/3.12도 호환된다. 기존 Qt 핀은 3.13을 지원하므로 새 패키지는 추가하지 않는다. 다른 minor의 환경은 새로 준비하고 기존 설정/환경은 보존한다. 데이터 이전은 없고 복원 시 이전 코드·기존 환경을 재사용한다. [검증 기록](../testing/runs/20261113-connector-python313.md). 고정 제품 SHA와 Windows CI는 게시 후 이 절에 추가한다. 회사 Z: 경로 문제와 실제 GUI·SSH·장비 인수는 별도다.
