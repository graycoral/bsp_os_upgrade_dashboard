# TEST BOARD CONNECTOR 표시명 변경

사용자가 확정한 이름은 **TEST BOARD CONNECTOR**다. Windows는 실행 환경이고 기능 설명은 보드 연결·이미지 설치·테스트 실행이다.

원본 기준은 `11981b454efa7edb96da51817c64fd75896f2ed7`, 명칭 후속 코드/시험 커밋은 `b122c57e40137be48b29dc5477ca462d5523facb`다. Dashboard/단독 GUI 배너·소스 준비 안내, 설정 CLI/시작/연결 오류, 서버/플러그인 참조 클라이언트의 진단 메시지, 편집형 배포 README와 현재 사용자·PORT 안내를 갱신했다. `tests/e2e/gui-test.spec.ts`의 기존 GUI-UI-16 표시명 assertion도 새 이름으로 맞췄다. 기존 `windows-runner` 파일명·ZIP 경로·API 코드/필드·클래스·설정·토큰·DB/runtime·실행 명령은 유지한다. 이름 변경을 위한 데이터 이전·재설치는 없다. 새 EXE/ZIP은 만들지 않았다.

## 검증

전체 stdout/stderr는 아래 로컬 전용 경로에 보존하며 Git에 포함하지 않는다. 최초 시도의 실패를 지우지 않았다.

| 확인 | 결과 | 로컬 로그 |
|---|---|---|
| 최초 표시명 빌드 (기존 Node 22.23.2 사용) | PASS / exit 0, Dashboard·단독 GUI 두 빌드 | `.local-reports/board-connector-name-14281018b1/build.log` |
| 최초 설정 탐색·Windows 실행·플러그인 서비스/진단 기존 회귀 | exit 1; 70 PASS / 2 FAIL / 26 warnings. 모의 TC 프로세스 종료의 killpg EPERM 및 RUNNING 잔류 | `.local-reports/board-connector-name-14281018b1/pytest.log` |
| 확정 명칭으로 `bash scripts/build.sh all --skip-install` 재실행 | PASS / exit 0, 두 빌드 | `.local-reports/test-board-connector-68d4b6bd24/build.log` |
| 프로세스 제어 허용 환경에서 동일 기존 회귀 재실행 | exit 1; 69 PASS / 3 FAIL / 27 warnings. 프로세스 종료 EPERM/상태 완료 timeout이 남음 | `.local-reports/test-board-connector-68d4b6bd24/pytest.log` |

회귀 명령은 `.venv/bin/python -m pytest tests/test_setup_flashing_discovery.py backend/gui_test/tests/test_windows_runner.py backend/gui_test/tests/test_plugin_integration_service.py backend/gui_test/tests/test_plugin_integration_diagnostics.py -q`다. 실제 보드/SSH 대신 임시 파일·DB와 가짜 Python TC를 사용한다. 최종 실패는 `test_manager_actual_adapter_repeat_fail_and_no_job_sync`, exit-code/invalid-bytes의 비정상 종료 사례, `test_manager_confirmed_single_and_dual_commands_end_to_end`다. 해당 프로세스/상태 코드의 동작을 이번 명칭 변경에서 바꾸거나 시험을 약화하지 않았다. 이 결과를 전체 회귀 PASS로 표시하지 않는다.

브라우저 GUI-UI-16·실제 Windows/장비/회사 플러그인 인수는 NOT_RUN이다. 독립 리뷰 NOT_REVIEWED. 앞선 RQ-62 고정 커밋/해시는 이번 명칭 후속을 포함하지 않으며 [PORT-008](../../porting/PORT-008.md)에 구분한다.
