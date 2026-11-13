# 보드 커넥터 · 연결/콘솔 계약

RQ-63 / D-67. 사용자가 마지막으로 확정한 표시명은 **보드 커넥터**다. 이전 TEST BOARD CONNECTOR 명칭의 기계 코드·timeout marker·API·설정 경로·과거 실행 기록은 유지한다. 이 문서는 2026-11-12 로컬 구현 계약이며 실제 회사 Windows/SSH/장비 인수는 T-228 NOT_RUN이다.

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

실제 연결 종료는 중앙 Run의 RUNNING/QUEUED/PAUSED/UNKNOWN/삭제 진행과 Host 실행/배치 예약을 검사한다. Host의 connection-stop은 잠금 안에서 안전 여부를 확인하고 신규 TC/배치 수락을 fence한 뒤 관리자 종료 신호를 보낸다. 실패/확인 불가는 강제 종료로 우회하지 않는다. 사용자 지정 원격 서비스 포트는 바꾸지 않으며 회사 8765는 저장 프로파일 예시다.

GUI SSH는 BatchMode key/agent와 사전 OpenSSH host key 인증만 지원한다. 비밀번호/키 암호 프롬프트를 pythonw에서 자동 처리한다고 가정하지 않는다. 표준 OpenSSH 콘솔에서 먼저 인증한다. SSH -L은 probe 후 바인딩 경쟁이 가능하며 기존 ExitOnForwardFailure 실패를 표시한다. 임의 포트 점유자를 종료하지 않는다.

## 보드 콘솔과 오류 전달

보드 콘솔 원문은 기존 ConsoleObserver의 검증된 **RX 전용 splitter COM**만 읽는다. GUI/진단/API는 control COM을 다시 열거나 프롬프트를 소비하지 않는다. console_observers의 board별 RX/제어선 격리는 최초 한 번 명시한다. 상시 idle/일반 TC 관찰은 Host 내부 hub가 소유하고, 해당 보드 batch 준비 전에 기존 FlashService로 소유를 이전한다. 다른 보드의 관찰은 유지한다. batch observer는 board_id로 연결한다. GUI poll/구독 종료는 COM/observer/lease/fence/판정에 영향을 주지 않는다.

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

플러그인 허용 경로·서버 설정 principal·Run 소유권·멱등성·runner identity 고정은 유지한다. 사용자가 입력하지 않는 관리자 IPC 자격, 배치 lease, preparation 증표, 읽기 전용 브라우저 세션은 별도 목적이므로 유지한다. 구형 함수의 token 인자는 호환용으로만 받고 전송·비교하지 않는다. 세 서비스 환경변수와 기존 연결 토큰 파일도 사용하지 않는다. DB 이전은 없으며 Linux API/Worker·Windows 커넥터·플러그인 클라이언트를 함께 갱신한다.

## 단일 설치·실행 · RQ-65 / D-69

Windows 사용자 진입은 루트 `board-connector.cmd`로 통일한다. thin CMD는 Python Launcher의 3.13을 먼저 찾고, 없으면 기존 `.venv` 또는 Python Launcher/PATH에서 Python 3.13 64비트(3.11/3.12 호환)를 찾고 `scripts/board_connector.py`에 인자와 종료 코드를 전달한다. PowerShell 실행 정책을 변경하지 않는다. Python이 없으면 설치 주소를 표시하고 실패한다.

준비 코드는 두 기존 잠금 파일의 패키지 버전과 Qt/GUI import를 검사한다. 정상 환경은 네트워크 없이 재사용한다. 두 잠금 파일·Python ABI가 바뀌거나 환경이 손상되면 home/connector-environments의 새 경로에 설치한다. 동일 home 설치는 LaunchLock으로 직렬화한다. 성공 검증 후 선택 파일을 원자 교체하며 실패는 이전 설정·환경을 보존한다. 새 의존성·실행 API/DB 변경은 없다. 기존 관리자·Host 수명과 TC Python 분리는 유지한다.
