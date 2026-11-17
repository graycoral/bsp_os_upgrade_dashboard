# 보드 커넥터 자동 멀티플렉서

RQ-66/D-70 후속/T-273/REG-0104. 이전 기준은 `1da1da2173c84689662de669d6a95fb8775c7037`이다. 코드·시험 고정 커밋은 `59af913972b4898f9da37f4174816a3869be895e`다. 별도 worktree에서 이번 변경만 구현·검증했으며 다른 세션의 WIP를 포함하지 않는다.

## 변경

실제 COM을 선택하면 관리 시작 경로에서 멀티플렉서를 사용한다. 기존 native/필드 누락 프로파일은 시작·Host 잠금과 영속 작업/예약 상태 확인 후 백업하여 전환한다. 로컬 설정 저장과 공통 desired 적용도 같은 조건을 지킨다. RX·비공개 observer·비활성 보드 정보와 실패 기록은 보존한다.

TC 실행 전에 해당 Python 프로세스의 pySerial을 프록시로 연결한다. TC 소스·COM 인자·저장된 argv는 그대로다. venv 경로·prefix와 기존 .pth/시작 hook은 프록시를 설치한 뒤 처리한다. 매핑·지원 파일 무결성·초기화 실패 시 TC를 실행하지 않는다. 물리 COM 직접 연결로 우회하지 않는다. 화면은 모드/RX 선택을 제거하고 실제 Host mux 준비 전까지 적용 대기로 표시한다.

## 검증

macOS Python 3.11.7/Qt offscreen/Node 22.23.4/Chromium, 가짜 UART와 실제 자식 Python·로컬 HTTP를 사용했다. 전체 원본 로그는 아래 `.local-reports/` 경로에만 보관하며 Git에 포함하지 않는다.

```bash
QT_QPA_PLATFORM=offscreen python -m pytest -q backend/gui_test/tests/test_automatic_serial.py backend/gui_test/tests/test_auto_serial_proxy.py backend/gui_test/tests/test_serial_multiplexer.py backend/gui_test/tests/test_portable_host.py backend/gui_test/tests/test_board_connector.py backend/gui_test/tests/test_shared_control.py backend/gui_test/tests/test_shared_connector_control.py tests/test_setup_commands.py tests/test_windows_runner_bundle.py tests/test_setup_runtime.py tests/test_editable_runner_build.py
bash scripts/build-ui.sh --skip-install
python docs/testing/validate_docs.py
```

- 수정 전: 이전 코드에 미변경 `from serial import Serial`을 사용하는 Host 회귀를 적용하여 1 FAIL을 재현했다. 실제 COM을 열려다 자식 실행이 실패했다. `.local-reports/20261117-auto-serial-baseline/pytest.log`.
- 최종 Python: 295 PASS/11 SKIP, exit 0. `.local-reports/20261117-auto-serial-final/pytest-2.log`. SKIP은 Windows backend/frozen·번들 플랫폼 항목이다. 기존 httpx deprecation 경고 1건을 보존했다.
- 웹 브라우저: 16 PASS, 미러: 15 PASS, exit 0. `.local-reports/20261117-automatic-serial-ui/web-browser-1.log`, `mirror-browser-2.log`. 기존 native 설정·숨겨진 값 보존·실제 mux 확인 전 PuTTY 비활성·실제 receipt를 확인했다.
- Agent Monitor/단독 GUI Test UI 빌드: PASS, exit 0. `.local-reports/20261117-auto-serial-final/build.log`.
- 초기 시도 중 잘못된 시험 파일 경로 2회, 변경된 RX/자동 이전 계약에 맞지 않던 기존 기대값, 시험의 json import 누락을 수정했다. `auto-serial-root-01`부터 `06`까지 실패·재시험 로그를 보존한다. 과거 실패를 덮어쓰지 않았다.
- 독립 리뷰로 로컬 저장의 UNKNOWN 이전 우회와 venv 설정 파싱/prefix 문제를 발견하고 수정했다. 새 venv 시험의 Homebrew 시작 hook 차이를 같은 일반/관리 실행 조건으로 맞춘 뒤 재시험했다. 초기 `auto-serial-final/pytest.log`의 2 FAIL과 `auto-serial-proxy-06` 로그도 보존한다.

## 독립 리뷰

Astra/xhigh 별도 세션에서 코드·계약·시험을 검토했다. 최종 판정은 APPROVED다. 독립 재시험 115 PASS/1 SKIP, exit 0과 diff 검사를 확인했다. 로그는 `.local-reports/20261117-independent-serial-review/final-targeted-2.log`에 보관한다. 사용자 지정 Sol 구현/Astra 리뷰 역할을 사용했으며 Claude 리뷰로 표시하지 않는다.

## 회사 확인

Windows 11/Python 3.13·실제 UART 드라이버·회사 TC 공통 모듈·PuTTY·SSH 인수는 NOT_RUN이다. 별도 Python subprocess·네이티브 프로그램·OS COM 핸들·inter_byte_timeout·RS485는 자동 변환 대상이 아니다. 새 가상 COM 드라이버·EXE·배포 ZIP을 만들지 않았다. TC Python의 기존 pySerial 설치는 필요하다.

플러그인·Agent Monitor·Windows별 적용은 [요청서](../../agents/BSP_UPGRADE_PLUGIN_REQUEST.md#2026-11-17--보드-com-멀티플렉서-자동-적용), 파일 목록·이전·복원은 [PORT-009](../../porting/PORT-009.md#2026-11-17--자동-멀티플렉서), 사용법은 [가이드](../../gui_test/TEST_BOARD_CONNECTOR_GUI.md#최초-설정)를 따른다.
