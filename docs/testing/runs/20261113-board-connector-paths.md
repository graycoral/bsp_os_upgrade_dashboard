# 보드 커넥터 경로 표시 · 2026-11-13

RQ-63/D-67/T-229. 기준 `6cf5552d68e2be403dd54ccb2ca341580a5563f2`, 대상 로컬 미커밋 변경.

사용자가 플러그인의 Linux 경로 설정과 Windows 커넥터의 경로 확인을 요청했다. 연결 탭의 접힌 **경로 보기**에서 서버의 현재 선택 TC 소스, 해당 실행의 BAT/TC 원본, Windows 이미지/TC 작업 폴더를 읽기 전용으로 표시한다. 이미지 선택·플래싱 시작 버튼과 경로 입력은 추가하지 않았다.

등록 응답의 선택 필드 `server_paths`, Host 최근 실행 응답의 `execution_paths`, 기존 job JSON의 `working_directory`를 추가했다. DB 스키마·실행 요청·멱등 해시·판정·예약은 유지한다. 서버가 runner별 Run을 선택하고 GUI는 그 Run의 batch/실행 ID와 일치하는 Windows 기록만 사용한다. 현재 선택 소스로 과거 실행 경로를 덮어쓰지 않는다. 구버전 필드 누락·요청 전·준비 전·완료·단절을 구분한다. 경로 표시가 전송/플래싱/파일 존재 확인을 대신하지 않는다.

원본 로그·스크린샷·manifest는 `.local-reports/board-connector-paths-20261113/`에만 보존한다.

| 실행 | 결과 | 근거 |
|---|---|---|
| `PATH=/usr/bin:/bin:/usr/sbin:/sbin QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q backend/gui_test/tests/test_board_connector.py backend/gui_test/tests/test_plugin_integration_pipeline.py backend/gui_test/tests/test_windows_runner.py` | 69 PASS / 3 FAIL | focused.log; Mac killpg EPERM으로 실행 스레드의 종료 확인 실패 |
| 위 범위 + `tests/test_api.py tests/test_gui_dashboard.py` | 105 PASS / 1 FAIL | retry-host.log; 앞 세 실패 통과, 다른 기존 응답 유실 fixture에서 같은 Mac killpg EPERM |
| `test_windows_runner.py::test_lost_start_response_does_not_duplicate_execution` | 1 PASS | retry-single.log; 프로세스 종료 확인 코드는 바꾸지 않음 |
| 같은 Qt widget offscreen 렌더링 | PASS | qt-render.log/paths.png; 780×560, 읽기 전용 경로·스크롤 표시 확인 |

T-229의 원본/선택 분리·runner 고정·준비 후 실제 작업 경로 기록·부모 이미지 경로 유지·삭제 제외·URL 마스킹·Qt 읽기 전용/stale 시험은 통과했다. 광역 단일 실행 전체 PASS로 표현하지 않는다. 소스/시험 SHA256은 로컬 manifest와 TEST_RESULTS.csv에 기록했다. 독립 리뷰는 NOT_REVIEWED다.

가이드의 플러그인 플래싱 절차와 이미지/BAT 전달 다이어그램, 계약·요구사항·시험 목록·PORT-009·현재 상태·진행 기록을 함께 갱신했다. 실제 Windows·SSH·회사 BAT/보드 검증은 NOT_RUN이며 새 EXE/ZIP·commit/push는 수행하지 않았다.

문서 검사 PASS: 상대 링크 1,246·요구사항63·시험229·오류0 (`docs.log`). `git diff --check` PASS (`diff.log`).
