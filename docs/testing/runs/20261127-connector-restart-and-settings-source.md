# Windows 강제 종료 후 재시작과 Linux 공통 설정 조회

## 프로필에 실행 중인 대상이 없는 경우

RQ-71 · T-271 · REG-0136. 기준 `e35f195`, 고정 코드·회귀시험 `9fbd611600689ff11d878acf35ffc7f1c7f3d041`. 기준에서 5개 시험이 실패했다. 무관한 고아 프로세스와 이전 트리 플래그, UTF-8 BOM과 UTF-16 BOM 각각의 정상 시작, 실제 잔존 프로세스 표시, CP949 파이프 오류 출력이다. 추가로 부모 정보가 없는 구형 SSH 기록과 별도 SSH를 함께 두는 시험에서도 수정 전 실패를 확인했다.

구형 기록을 정상 시작에서 반복 검사할 때 최초 트리 조회 실패 시각을 잃는 추가 시험도 실패했다. 후속 수정·시험 `c024a9446da83c18afdccaf4fa7c1ac6333708ec`에서 최초 증거 시각을 유지하고 단일 복구본에도 구형 SSH 후보 목록을 남긴다.

GUI 시작과 CLI 준비는 프로필 잠금 아래 현재 기록된 세대, CIM에서 확인한 프로필 프로세스, 구형 부모에 연결된 후보와 잠금을 검사한다. 현재 대상이 없으면 재시작할 수 있다. 후보로만 관찰한 자식은 종료 대상에 승격하지 않는다. 예전 시험의 전역 고아 조건을 이 프로필에 기록한 부모로 바꿔 연결된 자식은 계속 차단되는지 검증했다. 종료 누락 가능성이 있던 과거 실행 상태는 UNKNOWN이다.

`tests/test_force_stop.py`, `tests/test_board_connector_launcher.py`, `tests/test_setup_runtime.py`, `tests/test_direct_connector_unit2.py` 전체에서 162 PASS, 35 SKIP. macOS Python 3.11의 과정 모의 및 로컬 프로세스 검증이다. Windows 전용 시험은 실제 프로필 잠금·BOM 및 한글 경로 오류를 파이프로 전달하는 경우를 포함한다.

## TC 경로가 바뀌지 않는 경우

RQ-81 · T-302 · REG-0137. 수정 `72c4c2f37577ee53cfbede9b28faec237d6263d1`. 변경 전 Linux 플러그인 명령, SSH 설정 API, SSH로 읽는 SQLite의 출처를 확인하는 세 시험이 실패했다. 기존 응답은 사용한 파일·API를 버렸고 수동 조회 성공 문구에는 값이 없었다.

- POSIX 셸에서 실제 curl·loopback HTTP와 읽기 전용 SQLite를 검증했다. 정상·미설정, HTTP 200 빈 본문과 빈 객체, HTTP 거부, DB 누락·다른 런타임을 구분한다. 수동 SSH 조회는 자동 조회 캐시를 건너뛴다.
- 로컬 임시 home 및 runtime에서 플러그인 진입점 `apps/agent-monitor/plugin.py … settings show`를 실행했다. 반환한 `settings_db_path`가 실제 지정 파일과 일치했고 `tc_root_state=UNSET`, `tc_root=""`였다. 설정 저장 후 SET도 명령 시험으로 확인했다.
- Chrome Playwright에서 수동 조회 출처·미설정·동일 경로, 서버 변경 시 자동 갱신, 기존 경로 편집·보존까지 3 PASS.
- Python 회귀는 `tests/test_ssh_bind_probe.py`, `tests/test_direct_connector_unit*.py`, `backend/gui_test/tests/test_{connector_web,shared_control,shared_connector_control,connector_bootstrap}.py`를 실행했다. 195 PASS. 추가한 SET 시험의 초기 입력에 읽기 전용 revision을 포함해 한 번 실패했고, 저장 계약에 맞는 입력으로 수정해 전체 재실행했다.

회사 Windows 계정·Linux 실제 설정 파일·장비 인수는 NOT_RUN. GitHub Actions와 현지 결과는 독립적으로 확인한다. 데이터베이스 이전은 없다.
