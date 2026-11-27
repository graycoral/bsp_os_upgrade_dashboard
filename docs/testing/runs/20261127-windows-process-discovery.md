# 20261127-windows-process-discovery

RQ-71 · T-271 · REG-0129. 기준 `65ec647b4fb292be9e058b841f380fca3a5b5f4a`, 코드와 시험 `6490a7ecc4dcb82b7b2c3359e28ef540cfc29abc`.

| 검증 | 결과 |
|---|---|
| 수정 전 Manager와 실행 기록이 없고 독립 Host와 터널이 남은 상태 | 로컬 종료 완료를 반환한 뒤 두 프로세스가 살아 있어 1건 FAIL |
| 같은 상태에서 Windows 실행 목록 모의 | Host·SSH 종료, 별도로 실행한 SSH 보존 |
| 실행 명령 및 인터프리터 판별 | 해당 프로필의 Manager·Host·웹/Qt 런처·전용 Python·주/대시보드 SSH 식별. 다른 프로필·수동 SSH·경로 문자열만 포함한 공용 Python·종료 명령 제외 |
| CIM 조회 도중 PID 재사용 | 생성 시각이 달라진 프로세스 보존 |
| 조회 실패와 재시도 | 기록이 있는 대상 먼저 종료, 최종 조회 실패는 PENDING, 조회 복구 후 재검사 |
| 로컬 고정 코드 회귀 | `tests/test_force_stop.py`, `tests/test_setup_runtime.py`, `tests/test_direct_connector_unit2.py`, `tests/test_board_connector_launcher.py` 합계 127 PASS, 30 SKIP. macOS Python 3.11. 별도 OpenSSH 루프백을 포함한 개발 중 관련 시험은 148 PASS, 30 SKIP |
| Windows 전용 실제 프로세스 시험 | 기본 Windows CI 대상인 `tests/test_board_connector_launcher.py`에 임시 Python 프로세스와 실제 `ssh.exe` 핸드셰이크 시험 추가. 두 프로필 또는 수동 터널을 함께 띄워 한쪽만 종료되는지 확인. macOS 실행에서는 SKIP |

편집형 번들의 실제 배치 파일이 사용하는 `-B -X utf8 -m scripts.setup_runtime`도 패키지 배치·인터프리터 경로와 프로필을 대조해 식별한다. 후속 커밋 `270449da4d981b01caae53015fb3d79ef1ffec35`에서 관련 네 시험 파일 128 PASS, 30 SKIP. 동일한 SSH 생성 코드에 대한 별도 루프백·프로브 시험 21 PASS.

GitHub Windows 실행기(Python 3.13)에서 추가한 Python·OpenSSH 실제 프로세스 시험 2건이 모두 통과했다. 같은 파일의 마지막 두 시험이며 pytest 진행 출력의 마지막 두 결과는 PASS다. `65ec647` 기준 1003 PASS / 15 SKIP / 9 FAIL에서 `d8edcfd`는 1005 PASS / 15 SKIP / 9 FAIL이었다. 기존 실패는 직렬 출력 줄바꿈 4건, 프로필 검증 2건, Windows 시그널 2건, 공유 경로 1건으로 동일하다. Ubuntu 전체 회귀의 기존 설정 파일 바이트 비교 실패 3건도 같은 시험에서 반복됐다. [Windows 기준 실행](https://api.github.com/repos/graycoral/bsp_os_upgrade_dashboard/actions/jobs/140278684264) · [Windows 재시험](https://github.com/graycoral/bsp_os_upgrade_dashboard/actions/runs/45930110616/job/140280534738) · [Ubuntu 재시험](https://github.com/graycoral/bsp_os_upgrade_dashboard/actions/runs/45930110616/job/140280535058)

회사 Windows 권한 정책, 회사 SSH 서버, 실제 보드 T-272는 NOT_RUN. [운영 안내](../../gui_test/FORCE_STOP.md)
