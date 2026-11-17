# GUI 실행기의 서버 포트 옵션

RQ-65/T-232 후속. 선행 기준은 `41ba537aeb88c7a926302070b15b5d0b55520863`이며 코드·시험 고정 커밋은 `8849a281cb16618b3ae2cb78fbe209f4687af360`다. 별도 worktree에서 검증했고 다른 세션의 미완료 변경은 포함하지 않는다.

## 동작

`board-connector.cmd --server-port 8765`와 별칭 `--remote-dashboard-port`를 지원한다. 설치용 Python에서 GUI Python으로 옵션을 전달하고 Manager가 값만 검증·저장한다. 생략 시 저장값을 덮어쓰지 않으며 최초 기본은8766이다. 연결 JSON과 함께 지정하면 CLI 값이 우선하며 원본 JSON은 수정하지 않는다. 설정 화면도 같은 저장값을 표시한다.

연결/시작 중이거나 RUNNING·UNKNOWN·예약이 남으면 다른 값의 적용을 거부한다. 같은 값은 멱등 처리한다. loopback 인증·브라우저 거부·Manager 제어 잠금·시작/Host 잠금·영속 기록 검사를 유지한다. 최초 보드/SSH 미설정 상태에서도 포트만 저장할 수 있다. 서비스 identity·COM·비공개 필드와 기존 설정 백업을 보존한다.

## 검증

macOS Python3.11.7, Qt offscreen, 모의 설치/Manager·로컬 HTTP를 사용했다. 실제 Windows CMD/SSH/장비는 실행하지 않았다.

```bash
QT_QPA_PLATFORM=offscreen python -m pytest -q backend/gui_test/tests/test_connector_server_port.py backend/gui_test/tests/test_connector_bootstrap.py backend/gui_test/tests/test_board_connector.py backend/gui_test/tests/test_connector_web.py tests/test_board_connector_launcher.py tests/test_runner_ports.py
python docs/testing/validate_docs.py
```

- 최종 회귀 212 PASS/13 Windows SKIP, exit0. `.local-reports/20261117-server-port/pytest-3.log`.
- 첫 범위 90 PASS/12 SKIP. 확장 시 시험의 불완전한 포트 프로파일 입력 1건과 이전 계약을 가정한 포트 시험 2건이 실패했다. 입력을 전체 프로파일로 고쳤고 Windows 자동 proxy 이전/원본 백업 및 Linux manage.py의 정확한 argv/cwd/env/실패 전달로 시험을 갱신했다. 초기 로그 `pytest-1.log`와 `pytest-2.log`도 보존한다.
- 잘못된 포트는 설치·Manager 시작 전에 거부한다. IPC 권한/입력, 시작 잠금, UNKNOWN/예약, 서버/역방향 포트 충돌, 저장값 유지, bootstrap endpoint·identity 보존, import-only 무기동, 이전 Manager404 안내를 확인했다.
- 제품 UI 코드 변경이 없어 UI 빌드는 실행하지 않았다. 실제 Windows11/Python3.13 CMD 및 회사 SSH 인수는 NOT_RUN이다.

## 독립 리뷰

Astra/xhigh 별도 세션에서 검토했다. 충돌 오류의 HTTP500을422로 바꾸고 import 결과가 실제 덮어쓴 endpoint를 반환하도록 수정했다. 최종 판정은 APPROVED다. 독립 재시험도212 PASS/13 SKIP, exit0이며 `.local-reports/20261117-independent-server-port-review/final-targeted.log`에 보관한다. Claude 검토나 회사 인수로 표시하지 않는다.

전체 원본 로그는 로컬 `.local-reports/20261117-server-port/`에만 보관한다. [사용법](../../gui_test/TEST_BOARD_CONNECTOR_GUI.md#서버-포트-지정), [PORT-009](../../porting/PORT-009.md#2026-11-17--서버-포트-실행-옵션), [플러그인·Agent Monitor 전달](../../agents/BSP_UPGRADE_PLUGIN_REQUEST.md#2026-11-17--커넥터-실행-시-서버-포트-지정)를 함께 적용한다.
