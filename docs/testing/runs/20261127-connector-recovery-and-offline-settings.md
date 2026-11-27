# 2026-11-27 · 강제 종료 재확인 및 오프라인 Linux TC 설정 읽기

기준 main `ce006b8f3016baa339e36dfa1fdbfe63846b4caf`. 환경은 macOS, Python 3.11, 임시 프로필, loopback OpenSSH 및 SQLite다.

## REG-0132 · SSH와 Python이 0이어도 GUI 재시작 불가

RQ-71 · T-271. 기존 버전에서 Windows 프로세스 목록에 후보가 없고 CIM이 응답하지 않는 경우와 자식 조회가 끊긴 뒤 모든 소유 프로세스가 사라진 경우를 모의했다. 두 회귀시험 모두 실패했다. 이전 코드는 후보가 없어도 CIM을 호출했고, 이전 트리의 `tree_unverified` 기록이 남으면 현재 상태를 확인하기 전에 같은 예외를 냈다.

수정 `e2d9c5b4d462d5669cbd1f8a00cc485f6f5cdeee`. 비어 있지 않은 Win32 스냅샷에서 보조 조회 대상이 없으면 그 사실을 사용한다. 중단된 종료 이력은 프로필 프로세스·잠금과 Windows 프로세스의 부모·생성 시각 또는 중간 재부팅을 대조한다. 기록이 갱신된 뒤 GUI 시작 검사가 통과하는지, Python/SSH가 아닌 고아 프로세스와 재사용 PID가 있을 때 미확인 상태를 유지하는지 시험했다.

| 로컬 재시험 | 결과 |
|---|---|
| `tests/test_force_stop.py`, `tests/test_board_connector_launcher.py`, `tests/test_setup_runtime.py`, `tests/test_direct_connector_unit2.py` | 136 PASS, 31 SKIP |
| Windows 네이티브 CIM·프로세스 생성 시각 및 이전 부팅 기록 복구 | 로컬 NOT_RUN. Windows 런처 시험 파일에 포함 |

## REG-0133 · 설정 API와 플러그인이 없을 때 Linux TC 경로 수신 대기

RQ-81 · T-302. 임시 Linux 계정 홈에 가상의 회사 런타임 위치를 등록하고 실제 공통 설정 DB에 TC 경로를 저장했다. TCP 설정 포트를 닫고 플러그인 보고 없이 기존 SSH 조회 함수를 실행했다. 수정 전에는 저장된 경로 대신 `None`을 반환해 새 회귀시험이 실패했다.

수정 `efe8847a42a7fac35117826a860b6ba3c0864702`. 일반 직결 프로필에서 설정 API 연결이 거부되면 같은 로그인 계정의 기존 DB에서 표시할 설정을 읽는다. API의 HTTP 거부, 구형 서비스 고정 프로필, DB에 지정된 커넥터 불일치는 각각 실패로 처리한다.

| 로컬 재시험 | 결과 |
|---|---|
| 루프백 OpenSSH, 읽기 전용 DB, 커넥터 supervisor, 공통 설정, 웹·Qt 설정 조회 API 및 bootstrap | 191 PASS |
| DB 누락·대상 불일치·HTTP 거부, 빈 TC 경로, 원본 DB 바이트와 회사 메타데이터 보존 | PASS |
| 별도 설치 home을 쓰는 회사 Linux, 실제 회사 Windows와 장비 | NOT_RUN |

## 회사에서 확인할 순서

1. 진행 중인 TC·플래싱이 끝난 뒤 갱신한 Windows 커넥터 폴더에서 기존 프로필로 `.\board-connector.cmd --force-stop`을 실행한다. 로컬 `FORCE_STOPPED`를 확인한다. 서버 포트가 `BUSY`이면 출력된 점유자를 확인한다.
2. 같은 프로필로 `.\board-connector.cmd`를 실행해 연결한 뒤 환경설정에서 **서버 공통 설정 불러오기**를 누른다. 정상 수신이면 Linux에 저장된 경로나 경로 미설정 상태가 나타난다.
3. DB 누락이나 SSH 명령 오류가 표시되면 회사 플러그인을 사용하는 동일한 Linux 런타임에서 `bsp gui_test settings show` 결과의 `shared_settings.integration.tc_root`를 확인한다. 별도 설치 위치에서는 같은 런타임의 `bsp gui_test connect`로 연결 보고를 보낸 뒤 다시 조회한다. 회사 계정에서 해당 명령이 성공하는지와 실제 저장된 경로는 미확인이다.
