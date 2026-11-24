# Windows 커넥터의 구형 SSH 기록 자동 정리

RQ-71/77 · T-271/292 · REG-0126. 원본 HEAD `35cde2f`에 로컬 후속 수정이 있는 환경에서 시험했다. Windows OS 동작은 프로세스 테이블·생성 시각·잠금·종료 핸들을 모의로 검증했다. 원본 로그는 로컬 `.local-reports/connector-auto-cleanup-sLQo7w/`에 있다.

| 시험 | 결과 |
|---|---|
| 구형 런처 종료, SSH 식별자 누락 | 수정 전 `red.log` 2건 FAIL. 남은 SSH가 없어도 강제 종료 전에 차단돼 이 설치본의 Host가 남았다. |
| 현재 설치본 정리와 재시도 | 다른 부모의 SSH 보존, 재사용된 부모 PID 제외, 확인된 Host 종료, 소유권 불명 SSH 생존 시 pending, 권한 실패·재시작 차단 및 후속 재검사. |
| 강제 종료·직결·웹 회귀 | `test_force_stop.py`, `test_direct_connector_unit{1,2,3,4}.py`, `test_direct_connector_unit5_and_security.py`, `backend/gui_test/tests/test_connector_web.py`에서 106건 PASS, Windows 전용 Toolhelp 실측 1건 SKIP. `full-stop.log` |
| 단일 종료 스크립트 | [배포 파일](../../../deliveries/connector-recovery/stop-board-connector.py) 하나만 임시 폴더에 복사해 독립 실행 경로를 검증했다. 타 설치 SSH 보존, 이 설치의 Host 정리, 불명 SSH의 pending과 재시도 완료를 확인했다 (`one-file-confirmed.log`). Windows 실기 미실행. |
| Client 정상 종료 오류 | Manager가 안전 상태를 조회하다 시간 초과하거나 Host가 500을 반환한 두 경로에서 수정 전 IPC가 일반 HTTP 500을 반환했다 (`client-500-red.log`). 수정 후 503 또는 502와 `STOP_READINESS_UNAVAILABLE`를 반환하며 보드를 정지하지 않는다. 종료/직결/웹/기존 연결 모드 회귀 113건 PASS, Windows 전용 1건 SKIP (`final-backend.log`). 회사에서 본 500의 내부 원인은 미확인이다. |
| 웹 브라우저 | 전체 모의 시험 25건 중 19 PASS, 6 FAIL (`browser.log`). 새 SSH 재연결 중 안전 종료·UNKNOWN 차단 시험은 PASS. 모의 콘솔 오류 문구 1건, T-308 파일 선택 안내 4건, 선택 모니터를 포함한 초록 신호등 4개 단언 1건은 FAIL. |
| 실제 회사 Windows·장비 | T-272 NOT_RUN. |

## 게시 전 재시험

커밋할 파일로만 구성한 사본에서 단일 스크립트의 CLI 진입점에 실행 중인 Host, 자식 작업, 다른 프로세스를 모의 입력했다. Host와 자식 종료, 다른 프로세스 생존, 중단된 작업의 `UNKNOWN` 기록을 확인했다. 처음에는 시험이 macOS 생성 시각 형식으로 Windows 시각을 비교해 자식 검증이 실패했다. 기존 Windows 모의 비교기를 적용한 후 재시험했다.

- `python -m pytest -q -rs tests/test_force_stop.py tests/test_direct_connector_unit*.py backend/gui_test/tests/test_connector_web.py tests/test_board_connector_launcher.py` 결과는 146 PASS, Windows 실측 전용 21 SKIP이다.
- Playwright에서 기본 연결·종료와 SSH 재연결 중 안전 종료 2건이 통과했다. 위 전체 브라우저 실행의 다른 실패 6건은 이번 집중 재시험 범위 밖이다.
- 원본 로그는 로컬 `.local-reports/force-stop-publish-CqbqvQ/`의 `backend-final.log`, `browser-final.log`에 있다. 실제 회사 PC의 종료는 미확인이다.
