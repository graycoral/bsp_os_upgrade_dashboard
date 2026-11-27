# 2026-11-27 · Windows 강제 종료 PermissionError

RQ-71 · T-271 · REG-0134. 기준 `807d0a5`, 코드·시험 `2e347d9c0a7695b831b0ab84001ebd3da4bfdd1d`. 회사에서는 SSH·Python을 종료한 뒤에도 대기가 계속됐고 마지막 오류는 `PermissionError`였다. 회사 PC의 PID·오류 단계·파일 경로는 미확인이다.

| 조건 | 수정 전 | 수정 후 |
|---|---|---|
| 저장된 SSH PID의 네이티브 조회가 거부되고 CIM 생성 시각으로 재사용이 확인됨 | 강제 종료 실패 | 새 프로세스를 보존하고 옛 SSH 기록을 정리한 뒤 GUI 시작 허용 |
| 생성 시각이 같거나 CIM에 값이 없음 | 예외 종류만 표시 | PID와 조회 권한을 표시하고 종료 대기 유지 |
| 확인한 소유 프로세스의 종료 핸들을 열 권한이 없음 | 예외 종류만 표시 | 명령 출력과 GUI에 같은 PID와 종료 권한 안내 표시 |
| 상태 파일 교체가 한 번 공유 위반으로 거부됨 | PermissionError | 기존 기록을 보존하고 잠금 해제 후 자동 갱신 |

수정 전 위 조건의 회귀시험 5개가 실패했다. 수정 후에는 PID가 조회 사이에 사라지는 경우, 생성 시각 차이가 정밀도 이내인 경우와 파일 권한 거부가 지속되는 경우도 확인했다. 로컬에서 `tests/test_force_stop.py`, `tests/test_board_connector_launcher.py`, `tests/test_setup_runtime.py`, `tests/test_direct_connector_unit2.py` 실행 결과 144 PASS, 32 SKIP. macOS Python 3.11에서 Windows의 오류를 모의했다. 실제 Windows 파일 공유 시나리오는 Windows 런처 시험에 포함했다.

회사 인수는 NOT_RUN이다. 갱신한 커넥터에서 동일 계정·프로필로 한 번 실행해 최종 상태 또는 구체적인 권한 안내를 확인한다. [운영 절차](../../gui_test/FORCE_STOP.md)
