# PORT-009 · 보드 커넥터 GUI와 공통 연결/콘솔

상태: 로컬 소스 구현·모의 검증, 회사 T-228 NOT_RUN. RQ-63/D-67/T-222~228/REG-0079. [설치·사용·연동 가이드](../gui_test/TEST_BOARD_CONNECTOR_GUI.md), [계약](../design/BOARD_CONNECTOR_CONTRACT.md), [실행 기록](../testing/runs/20261112-board-connector-gui.md).

기준 고정 커밋 `6734c843c46e986ce5c35a0851c38ac009661b98`; 제품·시험 대상 고정 커밋은 `ed3d2ac409ce586c0682637fba4c6f1989247e28`다. 후속 문서 커밋은 이 제품 대상을 변경하지 않는다. source SHA manifest는 게시 전 로컬 증거이며 현재 전달 비교에는 위 고정 커밋을 사용한다. 새 배포 ZIP은 없고 실제 회사 인수 전 운영 적용 완료로 취급하지 않는다. 기존 PORT-004/007/008과 timeout/영구 삭제 WIP를 함께 비교하고 회사 필수 정책·COMPANY_MAP/APPLIED를 먼저 확인한다.

## 파일과 회사 연결

- 재사용 Python: `backend/gui_test/connector/`(registry/console/settings/supervisor/gui/preview/logs/workers/api), 기존 execution Host/FlashService/batches/launch·WindowsRemote·core Manager/IntegrationService 접점.
- 재사용 UI: `packages/gui-test-ui/src/ConnectorStatus.tsx`, TestPage·test.css. capability opt-in이고 호스트 CSS --gt-*를 사용한다. 서버/TC catalog 없이 inventory부터 표시한다.
- 전체 호스트: backend/api/main.py의 pairing/기존 plugin auth·health adapter, backend/worker/main.py의 물리 DB별 단일 DashboardWorkers. standalone Worker를 회사 서버에 추가 기동하지 않는다.
- 참조 plugin: standalone/plugin_client.py의 inventory/board_console/connector_errors. 읽기 discovery와 기존 strict 실행 preparation을 구분한다. 회사 plugin 원본은 없으므로 현지 adapter가 이 계약을 소비해야 한다.
- 소스 진입: `python -m backend.gui_test.connector`, `apps/board-connector/launch.cmd`, 고정 Qt requirements.lock. 앱 pyproject에 connector package/desktop optional dependency/entrypoint 포함. 기존 editable builder의 새 Qt wheel 조립은 이 변경에서 실행하지 않았다.

서버는 GUI_TEST_RUNNER_TOKEN, 별도 GUI_TEST_CONNECTOR_REGISTRATION_TOKEN, plugin의 GUI_TEST_INTEGRATION_TOKEN을 보호된 설치 경로로 제공한다. Windows 등록 자격은 별도 DPAPI TokenStore, 제어 IPC 토큰은 관리자 자동 생성이다. endpoint는 인증된 loopback SSH reverse 왕복만 등록한다. 회사 8765는 기존 서비스를 가리키는 저장값이며 공통 기본 포트를 바꾸지 않는다. runner URL/COM은 회사 plugin에 복제하지 않는다.

공통 서버 TC 선택을 재사용한다. 새 `runner: registered` 모드는 선택적인 기존 windows-http URL fallback을 없앤다. integration의 누락 connection/runner ID/TC root는 공통 registry/source에서 읽되 기존 명시 설정과 Run snapshot을 우선한다. snapshot 전송이므로 Windows source_root는 새 설정에서 필수가 아니다. Z:/UNC 가변 직접 실행·새 GC·임의 원격 파일 탐색은 미구현이다.

## 데이터 이전·복원

기존 runtime/JSON/DB를 백업 후 보존한다. 새 registry DB는 additive sidecar다. 기존 source_root/플래시/추가 필드는 원자 저장·이름 있는 백업으로 보존한다. GUI에서 줄인 보드는 비활성 설정으로 보관하며 실행 기록은 지우지 않는다. 다른 runner identity는 자동 교체/이관하지 않는다. 복원은 안전 종료 후 이전 코드·프로파일과 새 registry DB를 함께 보존하는 방식이다. UNKNOWN/예약/삭제 진행을 숨기는 DB 삭제를 하지 않는다.

## 검증과 남은 인수

실행 명령/현재 결과는 위 실행 기록을 따른다. fake HTTP/serial/process·Qt offscreen·브라우저 fixture는 실제 Windows/회사 plugin 수신 근거가 아니다. 회사는 Qt 6.8.3 Windows wheel/오프라인 라이선스·무결성, OpenSSH key/agent·회사 포트, loopback reverse identity, 실제 RX splitter 분리와 보드별 수집·batch handoff, 창 닫기 후 시험 지속, 중앙 오류 cursor 재조회, 안전 종료/재접속을 검증한다. 기존 timeout/영구 삭제와 API request/catalog timeout을 분리해 회귀한다. 새 EXE/전달 ZIP은 생성하지 않았다. 사용자 지시로 위 제품 커밋과 이식 기록을 게시한다.

## 사용자 안내 전달

회사 전달 시 [보드 커넥터 가이드](../gui_test/TEST_BOARD_CONNECTOR_GUI.md)를 함께 제공한다. 설치 명령, Windows–Linux 연결도, 최초 인증 설정, 사용 순서, 예외 조치를 포함한다. 회사 소스 경로·서비스 포트·인증 공급 방식만 현지 값으로 맞추고 실제 토큰은 문서에 넣지 않는다.
