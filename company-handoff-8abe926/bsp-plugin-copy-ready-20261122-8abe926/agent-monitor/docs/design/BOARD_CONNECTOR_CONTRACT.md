# 보드 커넥터 · 연결/콘솔 계약

2026-11-19 직결 보드 커넥터·자율 실행·양방향 연결 진단(RQ-77~81 · D-83): Agent Monitor 없는 직결(`SSH -R` 8771 단독 완료)·보드 커넥터 자율 실행·양방향 연결 진단의 설계 및 로컬 구현(`T-291`~`T-304` PASS, 실장비 `T-305` NOT_RUN)은 [직결 상세 설계](DIRECT_CONNECTOR_ARCHITECTURE.md), [PORT-013](../porting/PORT-013.md), [구현 검증 기록](../testing/runs/20261119-direct-connector-implementation.md)을 따른다. 아래 기존 계약과 D-48 동작은 호환 경로로 함께 유지한다.

2026-11-15 RQ-70/D-75: Agent Monitor 보드 커넥터 탭과 양방향 설정·명령 결과의 현재 계약은 [미러 계약](BOARD_CONNECTOR_MIRROR.md)을 따른다. 기존 연결·UART·실행 소유권을 재사용하며 Windows 자동 시작을 추가하지 않는다.

2026-11-14 RQ-67: [플러그인 중심 공통 설정·실패 분석·설치 안내](../agents/PLUGIN_CONTROL_API.md). 최신 적용/검증 상태는 해당 안내를 따른다.


2026-11-14 목표 변경: 제품명 **Agent Monitor**, 설명 **bsp-os-upgrade**. 플러그인 중심 자동 플래싱·실패 분석, Agent Monitor·ACON·보드 커넥터 상호 연동과 커넥터의 공통 설정 변경을 [기능별 협의 문서](PLUGIN_CENTRIC_INTERFACE_PLAN.md)에서 확인한다. 기존 읽기 전용 범위와 구현 계약은 아래의 당시/현재 상태이며, 새 방향의 구현 완료를 뜻하지 않는다.

RQ-63 / D-67. 사용자가 마지막으로 확정한 표시명은 **보드 커넥터**다. 이전 TEST BOARD CONNECTOR 명칭의 기계 코드·timeout marker·API·설정 경로·과거 실행 기록은 유지한다. 이 문서는 2026-11-12 로컬 구현 계약이며 실제 회사 Windows/SSH/장비 인수는 T-228 NOT_RUN이다.

## 2026-11-14 웹 기본 화면·CMD 진단 후속

사용자 최종 지시에 따라 CMD와 모듈의 기본 UI는 browser이며 Qt는 `--ui qt` 호환 경로다. 같은 Windows Manager가 `/ui/<instance>/` 화면을 제공한다. 기존 비브라우저 IPC/Host/등록 인증 제한을 유지하고, 인증된 IPC가 발급한 60초 일회성 fragment 티켓을 instance별 HttpOnly/SameSite 쿠키와 CSRF 세션으로 교환한다. 정확한 loopback Host/Origin/port·본문 한도·CSP/no-store를 검사한다. 관리자 DPAPI bearer는 브라우저에 전달하지 않는다. 화면 세션은 메모리에만 두며 재시작 시 무효다.

로컬 설정 검사/revision 비교/저장과 연결/종료는 같은 Manager 제어 잠금으로 직렬화한다. 기존 미지 필드·`_setup` 추가값·RTS/DTR·비활성 보드·실행 기록을 보존한다. 웹 상태는 실제 `last_checked_at` 15초 기준으로 오래된 정보를 구분하고 새 HTTP 응답만으로 제어를 허용하지 않는다. COM 멀티플렉서/TC/PuTTY/플래싱 코어와 실행 판정 계약은 바꾸지 않는다. 공통 설정은 기존 shared_control 접점을 호출하고 로컬 저장과 중앙 적용을 구분한다.

기본 준비는 core lock만 사용하며 Qt import/설치를 하지 않는다. 고정 웹 자산은 재사용 뷰(`packages/gui-test-ui/src/connector_web`)와 호스트 연결(`connector/web_assets`)에서 source/wheel/bundle에 포함한다. CMD는 단계별 BC 코드·로컬 실행별 로그·명시 Python 경로·읽기 전용 진단을 제공한다. Z: 로컬 소스 캐시 배포/원격 Windows 자동 기동은 이번 변경 범위가 아니다.

[개선 설계](BOARD_CONNECTOR_WEB_GUI_PLAN.md), [사용/오류 해결](../gui_test/TEST_BOARD_CONNECTOR_GUI.md), [시험 기록](../testing/runs/20261114-connector-web.md), [Astra 리뷰 상태](../testing/runs/20261114-connector-web-review.md)를 따른다. 설계와 웹 GUI 구현 후 Astra xhigh 리뷰 APPROVED, 실제 Windows/회사 인수 NOT_RUN을 구분한다. 사용량 제한 실패와 최초 CHANGES_REQUESTED 이력은 리뷰 기록에 보존한다. 아래 Qt 계약/과거 검증은 호환 경로와 당시 이력으로 유지한다.

## 공통 등록과 실행 소유

전체 Dashboard의 기존 API와 Worker 프로세스는 `connector-registry.db`를 공유하는 `RegisteredWindows` facade를 사용한다. `gui-test.json`의 기존 windows-http+url은 legacy fallback이며 새 설치는 `runner: registered`로 endpoint 중복 입력을 없앨 수 있다. 데모와 실제 실행 DB가 다르면 기존 Dashboard 프로세스가 각 DB의 OS 잠금을 한 번씩 잡아 같은 Worker 구현으로 처리한다. 같은 DB를 두 번 배정하거나 standalone Worker를 추가 기동하지 않는다.

`POST /api/v1/gui-test/live/connector/register`는 loopback 비브라우저 요청만 허용한다. RQ-64 / D-68에 따라 Runner·등록·플러그인 연결 토큰은 요구하지 않는다. 서버는 HTTP loopback endpoint만 허용하며 identity→inventory 왕복 뒤에 등록한다. 새 runner identity로 자동 교체하지 않는다. 기존 hardware Run의 runner pin이 다르거나 기존 실행의 identity를 확인할 수 없으면 명시적 오프라인 이관이 필요하다.

Windows 관리자가 창과 독립적으로 3초마다 왕복·등록 heartbeat를 갱신한다. 등록과 console projection의 실제 수신 확인은 별도이며 둘 중 마지막 확인 15초 초과는 stale이며 새 작업의 board verify/시작을 차단한다. transport_generation은 endpoint 변경, config_revision은 runner+board mapping 의미 변경을 구분한다. 기존 Run/Attempt의 runner/source/connection/정책 snapshot은 보존하고 취소·삭제·복구를 다른 runner로 이동하지 않는다. 기존 plugin preparation/identity pin을 자동 덮어쓰지 않는다.

## Bootstrap과 TC 소유

소스/보드가 없는 Host도 부팅·등록·상태 조회가 가능하다. `/identity`의 `source_less_snapshot_v1`은 서버가 전송한 검증된 snapshot만으로 실행할 수 있음을 뜻한다. legacy source_root가 없으면 catalog/legacy 실행은 `SOURCE_NOT_CONFIGURED`로 거부한다. 외부 TC Python은 GUI Python과 별도로 유지한다. 미설정/접근 실패에서도 상태 bootstrap은 열리고 실행 준비만 TC_PYTHON_NOT_CONFIGURED로 차단한다.

소스 선택은 기존 서버 SourceService가 소유한다. Dashboard와 plugin이 같은 서버 선택을 읽고 connector에는 TC 폴더를 재입력하지 않는다. 서버 integration 설정에 connection/runner_id가 없으면 등록된 registry의 명시적 보드 순서 A/B와 runner identity를 읽어 새 preparation에 고정한다. 기존 명시 설정은 우선한다. tc_root가 없으면 선택한 서버 폴더 또는 이미 고정한 소스 저장소에서 얻는다. Linux 경로를 Z:/UNC로 추측하지 않는다.

최소 제품은 기존 **고정 snapshot 실행만** 지원한다. `/srv/tc`와 Windows Z:/UNC 직접 실행 대응은 현재 실행 경로에 필요하지 않으며, 가변 공유 원본 직접 실행 capability/Run mode는 미구현 요구로 남긴다. 기존 RQ-56/60 preview·token·재시도 보장을 바꾸지 않는다. 원본 삭제나 새 자동 GC도 구현하지 않는다.

## Inventory와 실행 가용성

`/v1/inventory`는 등록 보드 전체를 유지하며 기존 `/v1/boards`/verify는 감지된 COM만 허용한다. COM 열거는 포트를 열지 않으며 전원/부팅/PASS 증거가 아니다. board_id는 COM과 독립적인 저장 ID이고 runner와 함께 식별한다. 매핑 변경은 실제 Host/CLI 연결이 없을 때 저장하며 기존 Run의 snapshot은 유지한다.

행별 RUNNING/UNKNOWN/RESERVED는 대상 connection의 board_id로 계산한다. 다른 보드의 작업은 HOST_BUSY 대기 이유로 표시한다. 대상 불명 legacy 실행은 보수적으로 UNKNOWN으로 표시한다. host 전체 배타는 유지한다. 단절/재연결/색상 계산이 예약을 해제하거나 작업을 재실행하지 않는다.

Dashboard의 opt-in `connector_inventory_v1` UI는 TC 목록과 독립적으로 2초마다 inventory만 읽는다. 열린 화면에도 첫 등록/분리/오래된 상태를 반영하고 선택한 TC/기존 Run을 유지한다. 상태 갱신으로 TC 소스 전체를 반복 복사하지 않는다.

## 프로세스와 IPC

GUI는 별도 `connector.supervisor` 프로세스의 인증된 loopback IPC 클라이언트다. home별 LaunchLock, OS process creation identity, receipt, 분리된 DPAPI 제어 토큰을 사용한다. Host/SSH는 기존 Wizard·startup receipt·단일 runner.lock을 재사용한다. GUI 종료는 detach다. 관리자 heartbeat/Host/SSH/관찰은 GUI 없이 유지된다.

실제 연결 종료는 중앙 Run의 RUNNING/QUEUED/PAUSED/UNKNOWN/삭제 진행과 Host 실행/배치 예약을 검사한다. Host의 connection-stop은 잠금 안에서 안전 여부를 확인하고 신규 TC/배치 수락을 fence한 뒤 관리자 종료 신호를 보낸다. 정상 GUI 연결 종료에서 실패/확인 불가는 강제 종료로 자동 우회하지 않는다. 사용자가 직접 선택하는 별도 비상 명령은 아래 D-77 예외를 따른다. 사용자 지정 원격 서비스 포트는 바꾸지 않으며 회사 8765는 저장 프로파일 예시다.

GUI SSH는 BatchMode key/agent와 사전 OpenSSH host key 인증만 지원한다. 비밀번호/키 암호 프롬프트를 pythonw에서 자동 처리한다고 가정하지 않는다. 표준 OpenSSH 콘솔에서 먼저 인증한다. SSH -L은 probe 후 바인딩 경쟁이 가능하며 기존 ExitOnForwardFailure 실패를 표시한다. 임의 포트 점유자를 종료하지 않는다.

## 보드 콘솔과 오류 전달

아래 RQ-66 멀티플렉서 방식은 물리 COM의 내부 구독으로 원문을 수집한다. 기존 `serial_transport=native`에서는 ConsoleObserver가 검증된 **RX 전용 splitter COM**만 읽는다. GUI/진단/API는 control COM을 다시 열거나 프롬프트를 소비하지 않는다. console_observers의 board별 RX/제어선 격리는 최초 한 번 명시한다. 상시 idle/일반 TC 관찰은 Host 내부 hub가 소유하고, 해당 보드 batch 준비 전에 기존 FlashService로 소유를 이전한다. 다른 보드의 관찰은 유지한다. batch observer는 board_id로 연결한다. GUI poll/구독 종료는 COM/observer/lease/fence/판정에 영향을 주지 않는다.

Host `/v1/console?after=N&epoch=...&limit=4&error_after=M`는 읽기 전용 snapshot과 record 페이지다. cursor는 host epoch+단조 record seq이며 원본 byte offset과 마스킹 문자열 위치를 혼용하지 않는다. 각 보드 observer_epoch는 RX 소유 재생성을 구분한다. record 64개, 응답 최대 4개, 보드 text 4096자, 제한된 evidence event/gap으로 HTTP 2MiB 한도 안에 둔다. retained_from/reset/delivery_gap/history_truncated를 표시하며 UI 재생 누락은 실제 수집 gap과 구분한다. 원문 디스크 회전/수집 한도는 기존 observer 계약을 재사용한다.

Host가 생성한 durable 오류 큐를 error_after로 재조회한다. 등록 heartbeat가 마스킹한 console projection과 구조화 오류를 공통 서버 SQLite에 영속 저장한다. `/connector/console`은 마지막 공통 projection, `/connector/errors?after=N`은 event_id/seq 기반 증분 오류 조회다. runner/board/source/severity/code/time/phase/observer epoch/evidence reference 및 해당 execution의 중앙 Run/Attempt/batch 연결을 제공한다. 같은 event_id의 재폴링은 중복 삽입하지 않는다. 회사 plugin 코드는 없으므로 reference PluginClient의 inventory/board_console/connector_errors 소비와 모의 API 왕복까지만 검증한다. 서버 저장 acknowledgement는 회사 plugin이 실제 읽었다는 증거가 아니다.

소스 미설정 중에도 이 좁은 읽기 계약은 사용할 수 있다. 실행 메서드는 기존 health/config/prepared token 검사를 유지한다. CONSOLE_PANIC/GAP/미설정과 TC timeout/UNKNOWN을 사실대로 표시하며 임의 `error` 문자열로 PASS/FAIL을 만들지 않는다. 보드 콘솔/TC stdout·stderr/연결/플러그인 공통 오류는 별도 로그 탭이다. RX 미설정/단절을 정상 수집으로 표시하지 않는다.

## 데이터와 복구

추가 DB는 runtime의 `connector-registry.db`이며 registration/console_projection/connector_errors만 가진다. 기존 runs.db/executions.db는 기존 WIP timeout/영구 삭제 계약을 유지한다. windows-runner.json은 원자 저장과 백업으로 미지 필드/legacy source_root/플래시 설정을 보존한다. 줄인 보드 매핑은 connector_inactive_boards에 보관하며 실행 이력은 삭제하지 않는다. 복구는 서비스 안전 종료 후 기존 설정 백업과 새 DB를 함께 보존하고 이전 코드/설정을 복원한다. registry 삭제로 UNKNOWN/기존 Run identity를 우회하지 않는다.

## 경로 표시 · 2026-11-13

등록 응답의 `server_paths`는 현재 선택한 TC 소스와 해당 runner에 고정된 실행의 Linux BAT/TC 경로를 읽기 전용으로 제공한다. 실제 실행 중/UNKNOWN → 일시정지 → 대기 → 최근 완료 순으로 선택하고 Run ID·상태와 이전 실행 여부를 표시한다. 현재 선택 소스를 기존 실행의 원본 경로로 대체하지 않는다.

Host는 이미지 작업 복사 검증 또는 TC 작업 복사 완료 뒤 기존 job JSON에 `working_directory`를 추가한다. `/recent-executions`의 `execution_paths`는 실행 ID·batch ID·kind·state·작업 폴더만 전달한다. 최근 TC가 여러 개여도 같은 batch의 준비 기록을 조회하며 DELETED 기록은 제외한다. argv·프로파일·인증값을 노출하지 않는다. DB 스키마와 실행 요청·해시 계약은 바뀌지 않는다.

GUI는 서버의 실행 ID/batch ID와 일치하는 Windows 기록만 연결한다. URL 인증·query 정보와 제어문자를 제거하고 크기를 제한한다. 경로는 실행 입력으로 사용하지 않는다. 미수신/이전 실행/연결 단절을 구분하며 파일 존재·전송 성공·실행 성공으로 추정하지 않는다. 구버전 서버/Host에서 필드가 없으면 미수신으로 표시한다.

## 토큰 없는 서비스 연결 · RQ-64 / D-68

Runner·등록·플러그인 연결에는 공유 비밀을 전달하거나 비교하지 않는다. 참조 PluginClient는 비밀이 아닌 `X-Bsp-Service: plugin`으로 서비스 요청을 구분한다. 이 헤더는 인증 수단이 아니다. API는 loopback 접속만 허용하고 Origin/Sec-Fetch-Site가 있는 서비스 요청을 거부한다. 같은 머신의 비브라우저 프로세스는 이 서비스를 호출할 수 있으므로 OS 계정과 SSH 접속 권한을 신뢰 경계로 사용한다.

플러그인 허용 경로·서버 설정 principal·Run 소유권·멱등성·runner identity 고정은 유지한다. 사용자가 입력하지 않는 관리자 IPC 자격, 배치 lease, preparation 증표, 읽기 전용 브라우저 세션은 별도 목적이므로 유지한다. 구형 함수의 token 인자는 호환용으로만 받고 전송·비교하지 않는다. 세 서비스 환경변수와 기존 연결 토큰 파일도 사용하지 않는다. DB 이전은 없으며 Linux API/Worker·보드 커넥터·플러그인 클라이언트를 함께 갱신한다.

## 단일 설치·실행 · RQ-65 / D-69

Windows 사용자 진입은 루트 `board-connector.cmd`로 통일한다. thin CMD는 Python Launcher의 3.13을 먼저 찾고, 없으면 기존 `.venv` 또는 Python Launcher/PATH에서 Python 3.13 64비트(3.11/3.12 호환)를 찾고 `scripts/board_connector.py`에 인자와 종료 코드를 전달한다. PowerShell 실행 정책을 변경하지 않는다. Python이 없으면 설치 주소를 표시하고 실패한다.

준비 코드는 두 기존 잠금 파일의 패키지 버전과 Qt/GUI import를 검사한다. 정상 환경은 네트워크 없이 재사용한다. 두 잠금 파일·Python ABI가 바뀌거나 환경이 손상되면 home/connector-environments의 새 경로에 설치한다. 동일 home 설치는 LaunchLock으로 직렬화한다. 성공 검증 후 선택 파일을 원자 교체하며 실패는 이전 설정·환경을 보존한다. 새 의존성·실행 API/DB 변경은 없다. 기존 관리자·Host 수명과 TC Python 분리는 유지한다.

## 포트 멀티플렉서 · RQ-66 / D-70

관리 GUI/시작 경로는 `serial_transport=proxy`를 사용한다. 기존 native 또는 필드 누락 프로파일도 실행·예약·UNKNOWN이 없고 setup-launch/runner 잠금을 확보했을 때 백업 후 자동 전환한다. 설정 저장과 공통 desired 적용도 같은 종료 확인을 거친다. 숨겨진 RX·비활성 보드 설정은 보존한다. Host의 runner.lock 확보 후 Multiplexers가 물리 COM을 한 번 열고, 보드별 loopback RPC/Raw TCP 포트를 OS에 배정받는다. GUI는 IPC로 상태·제어를 요청하며 포트를 직접 열지 않는다. GUI 종료 후 Host/SSH/로그 수명은 유지한다. ADB USB 서버 프록시는 이 UART 변경과 별개이며 이번 구현에 포함하지 않는다.

TC는 기존 `import serial`·`from serial import Serial` 및 COM 인자를 유지한다. Host는 런타임의 코드 해시별 디렉터리에 bootstrap과 어댑터를 준비하고, TC용 Python에서 소스 실행 전에 pySerial 호출을 프로세스 내부 프록시로 연결한다. 원본 TC·저장된 argv는 보존한다. 프록시 설치 후 기존 패키지 경로·.pth·시작 hook을 불러오며 venv 설정을 유지한다. 초기화·해시 확인 실패는 TC 실행 전에 종료한다. 사용자가 토큰·포트·주소를 입력하지 않는다. 실행 lease는 서비스 연결 토큰과 달리 한 작업의 제어권/오래된 연결 거부용이며 설정·argv·DB·로그에 저장하지 않는다. 어댑터는 pySerial SerialBase를 사용하고 물리 COM fallback은 없다. 독립 Python subprocess·네이티브 COM 프로그램·OS 핸들·inter_byte_timeout·RS485는 자동 변환 범위 밖이다. 지원하지 않는 통신 옵션은 명시 오류로 반환한다.

물리 입력은 독립적인 유한 버퍼로 복제한다. 관찰 버퍼 넘침은 해당 구독의 gap이고, TC 버퍼 넘침·포트 분리는 실행 오류다. reset_input_buffer는 물리 입력의 현재 경계까지 관찰자에 전달한 뒤 해당 TC 구독만 비운다. RTS/DTR은 관찰자 접속으로 바꾸지 않으며 제어권 소유자의 명시 요청만 전달한다. 쓰기/flush 대기는 최대 2초로 제한한다. 통신 단절 후 자동 명령 재전송이나 포트 재개방은 하지 않는다.

기존 Host 실행/배치 배타에 수동 제어 게이트를 추가한다. 보드별 Raw TCP 연결은 하나이며 기본 읽기 전용이다. 수동 제어 부여 시 기존 읽기 연결을 닫고 새 연결만 송신하도록 해 이전 입력 재전송을 막는다. TC/예약/UNKNOWN 중 수동 제어는 거부하며 수동 소유 보드의 verify/실행/배치 예약을 거부한다. 프록시가 닫혀도 UNKNOWN 기록을 삭제하거나 완료로 바꾸지 않는다.

FlashService는 같은 멀티플렉서의 내부 제어 구독과 관찰 구독을 사용한다. fastboot 실행·이미지 검증·로그인/boot/panic signature·배치 예약·최종 사람 검토는 유지한다. native RX 코드는 과거 직접 Host 호환 경로로 남지만 관리 연결 UI에서는 선택하지 않는다. 기존 DB 스키마 변경은 없고 serial_transport/serial_settings/putty_path만 프로파일에 추가한다.

GUI는 기본 760×520, 선택 보드·PuTTY·수동 제어·접이식 로그 4탭을 제공한다. 같은 보드 행은 재생성하지 않고 동일 로그는 문서를 다시 쓰지 않는다. 증가분 로그를 묶어 추가하고 최대 1,000줄/64KiB 표시, 기존 로그 회전·gap 기록을 유지한다. [검증](../testing/runs/20261113-connector-multiplexer.md).


## 자동 정리 정책·보고 후속 · 2026-11-14

RQ-68: /v1/storage-policy 조회/CAS 저장과 /v1/storage-cleanup 예상·실제 정리를 제공한다. 서버가 명시 저장한 정책만 runner identity를 고정해 전달하고 연결 실패는 적용 대기로 보고한다. 로그·실패·UNKNOWN·보유 예약·재개 업로드는 자동 삭제하지 않는다. Windows 정리 결과는 중앙 API의 connector_cleanup.report에 있으며 UNAVAILABLE은 정리 성공이 아니다. 필드 원문은 [storage API](../../backend/gui_test/api/storage.py)와 [Windows retention](../../backend/gui_test/execution/retention.py), 운영은 [공개 안내](../agents/PLUGIN_CONTROL_API.md)를 따른다.


## PuTTY 입력 자동 연결 후속 · RQ-63/66 · D-74

새 기본 웹/Qt 화면은 별도 수동 제어 버튼 없이 PuTTY 열기에서 입력 제어권을 받는다. 보드 콘솔의 수신은 독립적으로 계속된다. Manager는 실제 fresh 상태와 실행·예약·UNKNOWN·기존 입력 소유를 확인하고 실행 파일 탐색 후 Host에 배타 grant를 요청한 뒤 PuTTY를 실행한다. Host는 기존 safe_to_stop/COM 게이트를 잠금 안에서 다시 검사한다.

Windows `/v1/serial-control`의 기존 `board_id`/`manual` 요청을 보존한다. 새 PuTTY 취득은 `manual=true, exclusive=true`를 사용하고 기존 수동 소유도 중복 취득으로 거부한다. 응답의 `manual_lease`는 이 호출에만 반환하고 inventory·argv·로그·DB에 저장하지 않는다. 종료/실패 정리는 `manual=false, lease=<받은 grant>`로 요청하며 mux 잠금 안에서 현재 grant가 같은 경우만 반환한다. 오래된 창 정리가 새 grant나 TC 소유를 해제하지 않는다. legacy bool 호출과 기존 Raw 연결 종료 반환도 유지한다.

프로세스 생성 실패 시 즉시 반환하고, Raw 연결 전에 창이 종료된 경우도 프로세스 종료 감시로 반환한다. 실제 소켓 연결 뒤의 창 종료는 기존 mux 경로로 즉시 반환한다. 새 Manager/Host/UI를 함께 적용하며 구버전 Host가 새 grant를 지원하지 않으면 입력 실행을 거부한다. 실행 판정·TC lease·기존 native 모드와 DB 이전은 변경하지 않는다. [검증](../testing/runs/20261114-connector-putty.md).

웹 상태의 connection_server는 실제 probe 시 읽은 서버/계정/SSH 포트만 전달한다. 화면에 남은 설정 초안을 서버 연결 근거로 사용하지 않고 fresh 연결에서만 보드 리스트에 주소를 표시한다. 키/비밀번호/전체 프로파일은 포함하지 않는다.

반환 통신 실패는 로그만 남기고 포기하지 않는다. 같은 grant를 1/2/4초부터 최대30초 간격으로 재시도하고 putty_cleanup에는 보드·RETRYING 상태·시도 횟수·마스킹 원인만 전달한다. 키는 노출하지 않는다. 반환 확인 전 같은 보드의 새 PuTTY 열기를 막고 성공/CAS 무효 확인 시 상태를 지운다.

자동 적용 후속 검증은 [20261117-automatic-serial](../testing/runs/20261117-automatic-serial.md), 회사 전달은 [PORT-009](../porting/PORT-009.md#2026-11-17--자동-멀티플렉서)를 따른다.

## 명시적 비상 강제 종료 · RQ-71/D-77

사용자 추가 지시로 Windows `board-connector.cmd --force-stop`, Linux Agent Monitor `run.sh force-stop`/`manage.py force-stop`을 제공한다. 정상 disconnect/stop, 창 닫기와 구분하고 오류의 자동 fallback으로 호출하지 않는다. [명령·상태·복구](../gui_test/FORCE_STOP.md)가 운영 안내다.

표준 라이브러리 경로에서 저장된 process 생성 세대를 검증해 해당 home의 관리 트리만 종료한다. Linux는 pidfd로 pin하고 SIGSTOP 실제 확인 후 자식 재귀 탐색·SIGKILL을 수행하며 탐색 실패 시 남은 pause를 해제한다. Windows는 OpenProcess handle과 creation time을 pin하고 부모 종료 후에도 handle을 유지해 PID 재사용을 막은 채 새 자식을 재탐색한다. snapshot 자식은 pin 이후 PPID를 재확인하고 발견 세대마다 즉시 checkpoint한다. 탐색/종료 불완전은 nonzero·pending이며 미확인 트리는 자동 성공으로 바꾸지 않는다.

Monitor는 service receipt에 supervisor/API/Worker 세대를 기록한다. Windows active-endpoints v1은 기존 필수 필드를 유지하고 선택적인 SSH transport identity를 추가한다. 고아 Host/SSH는 이 identity로만 종료하고, 이전 버전에 증거가 없으면 거부한다. GUI 시작·CLI 자식 준비와 force-stop은 home별 connector-start.lock으로 직렬화하며 pending marker는 신규 시작을 차단한다.

DB·예약·Run/Attempt·UNKNOWN 기록과 설정은 보존한다. API/Worker 또는 Manager/Host가 죽었다는 이유로 장비 실행을 PASS·종료 증명으로 바꾸지 않는다. 기존 Host/Engine recovery와 명시 복구 절차를 따른다. 실제 외부 Linux 작업·보드 상태는 로컬 종료 결과와 별개다. [구현·시험·Astra 검토](../testing/runs/20261117-connector-cleanup.md), T-271~272.

## 서버 포트 실행 옵션 · RQ-65 후속

관리 GUI 실행의 `--server-port`와 별칭 `--remote-dashboard-port`는 Linux Agent Monitor 포트다. 값이 없으면 저장값을 유지하며 최초 기본은8766이다. 명시 값은 Manager IPC를 통해 설정 파일에 저장하고 GUI와 공유한다. 연결 JSON 가져오기와 함께 지정하면 같은 원자 저장에 적용한다. 현재 연결·시작·영속 작업/예약·UNKNOWN이 있으면 다른 값의 적용을 거부한다. 동일 값은 연결을 유지한다. 서비스 identity와 다른 설정은 보존한다. 이전 Manager에서는 업데이트를 안내하고 별도 Manager나 오프라인 쓰기로 우회하지 않는다. SSH/Windows 로컬 포트는 이 옵션으로 변경하지 않는다. [PORT-009](../porting/PORT-009.md#2026-11-17--서버-포트-실행-옵션).

## TC 목록과 상태 조회 · RQ-73/D-79

커넥터는 TC 실행 제어를 추가하지 않고 공통 서버의 구조화된 Run 상태만 표시한다. 새 `GET /api/v1/gui-test/live/connector/test-status`는 기존 서비스 인증과 loopback 비브라우저 경계를 적용한다. TC 실행 명령·제어 lease·소스 적용·새 예약·별도 Worker를 만들지 않는다. Linux 미러 응답의 `test_status`도 서버가 직접 계산하며 Windows의 상태 게시를 TC 판정 근거로 사용하지 않는다.

공통 `integration.tc_root`가 있으면 그 폴더를 우선한다. 없으면 기존 대시보드의 적용된 frozen source를 사용한다. 둘 다 없으면 빈 목록과 설정 안내를 반환하며 legacy 원격 catalog나 Mock TC로 대체하지 않는다. 폴더는 기존 경로/링크·파일 수·크기 제한으로 읽고 공통 discovery로 `.py`를 분류한다. 스크립트를 import하거나 실행하지 않는다. 원본 파일 bytes의 snapshot identity와 기존 discovery의 줄바꿈 정규화 의미를 유지한다. 폴더 내용은 10초 간격의 캐시로 재확인하고 경로·metadata 변경은 다음 조회에서 즉시 무효화한다. frozen source 목록은 descriptor 변경 시 갱신한다.

응답은 `source`(표시 경로·종류·revision·목록 확인 시각), 상태 조회 시각 `checked_at`, `rows`(TC ID·상대경로·이름·보드별 상태), `stale`, `message`를 제공한다. 보드별 항목에는 원시 `state`, 표시 `label`, `run_id`, `run_state`, 완료 이력 여부 `historical`만 둔다. argv·로그·권한·실행 입력은 포함하지 않는다.

같은 runner·선택 경로·고정 소스에 해당하는 실제 Run 중 보드별 진행 작업을 우선하고 그렇지 않으면 최신 완료 작업을 표시한다. 플러그인 실행은 고정 receipt의 snapshot/revision, 대시보드 실행은 frozen source identity 또는 전체 파일 manifest/metadata를 대조한다. 단일 TC는 A 보드에만, Dual은 A/B에 연결한다. 다른 경로·다른 bytes·다른 runner·Mock 결과를 재사용하지 않는다. 반복/재시도 판정은 기존 `Run.results`를 그대로 사용한다.

| 서버 상태 | 표시 |
|---|---|
| PENDING / RUNNING / PASS / FAIL | 대기 중 / 진행 중 / PASS / FAIL |
| ERROR / TIMEOUT | FAIL · 실행 오류 / FAIL · 시간 초과 |
| UNKNOWN / CANCELLED | 확인 필요 / 취소됨 |
| 해당 Run에서 선택하지 않은 TC / 해당 보드 실행 없음 | 미선택 / 미실행 |

취소된 Run의 미수행 TC는 취소됨으로 표시한다. UNKNOWN Run의 미확정 TC는 확인 필요로 표시하고 이미 확정된 PASS는 보존한다. 경로 변경 후 이전 목록/결과는 제거하며 조회 오류·연결 단절은 과거 수신 정보로 표시한다. Windows 웹·Qt와 Agent Monitor 미러 모두 선택 보드에 따라 목록의 상태만 바꾼다. TC 목록에는 선택 입력·실행/중지/재실행 버튼을 두지 않는다. DB/의존성 변경은 없다. [실행 기록](../testing/runs/20261117-connector-test-status.md), T-280~281.

### 웹 커넥터 좌우 패널 · 2026-11-18

RQ-63/73·D-81: 웹 화면에서 보드 선택은 연결 단계 아래 가로 신호등 줄, 본문은 좌측 TC 조회/우측 콘솔·로그의 조절 가능한 패널이다. 기본30:70과 로컬 비율 보존, 독립 스크롤·조회용 TC 검색/필터를 제공한다. 서버 조회/상태·제어권 계약과 Qt/Agent Monitor 미러 배치는 변경하지 않는다. 상세 배치·접근성·좁은 창은 [화면 명세](UI_SPEC.md#2026-11-18-보드-커넥터-좌우-패널), 최소 브라우저 검증은 T-287와 [실행 기록](../testing/runs/20261118-connector-split.md)을 따른다.
