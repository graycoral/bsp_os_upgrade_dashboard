# 2026-11-12 CI 복구 · 최신 connector 통합

REG-0080; RQ-54/59/61/63, T-166/197/210/214/215/222~228 관련 회귀. 기준 `6cf5552d68e2be403dd54ccb2ca341580a5563f2`. 수정 revision은 이 기록을 추가한 로컬 커밋이며 코드·시험·workflow diff SHA-256은 `a18f8ddc6a9b6cf703f1bfc3a7c3c1e926d673c6906a200c53d18867f2325733`이다. 원격 게시·CI 재실행·릴리스는 하지 않았다.

## 실패와 수정

[전체 회귀](https://github.com/graycoral/bsp_os_upgrade_dashboard/actions/runs/43237132347)는 Linux 9 FAIL/1403 PASS/16 SKIP, Windows 3 FAIL/603 PASS/3 SKIP. [단독 Windows](https://github.com/graycoral/bsp_os_upgrade_dashboard/actions/runs/43237132364)는 두 PowerShell variant에서 wheel metadata 생성 중 `gui_test/connector` 부재로 실패하여 offline 설치를 실행하지 못했다.

- POSIX 전체 파일 flock 중복 획득을 단일 획득으로 수정. Windows bootstrap/child byte0/byte1 계약 유지. 독립 open 배제·예외 후 해제·marker 비우회·orphan child 시험 유지.
- 기존 포트 시험의 path keyword·receipt/PID/Host lock mock을 현재 시작 계약으로 갱신. SSH mapping·토큰 격리·설정 보존·소유 프로세스 정리 assertion 유지. 표시명 assertion 갱신.
- source-less connector bootstrap이 허용된 현재 계약에 맞게 frozen-host 시험을 수정. 상태 확인은 가능하지만 잘못된 외부 TC Python으로 실행하면 409/TC_PYTHON_NOT_CONFIGURED이며 프로세스·thread·snapshot이 생성되지 않음을 검증한다.
- exporter allowlist에 connector를 추가하고 실제 Python 파일 전부의 byte 보존 및 source ZIP/wheel staging 포함을 검증한다. upstream entry-point map 수정은 그대로 보존한다.
- 두 regression job에서 pyproject의 기존 desktop extras pin을 읽어 설치한다. Qt 시험을 skip하지 않으며 base runtime lock과 선택 의존성 경계는 유지한다.

## 실행 근거

Linux cloud, Python 3.12.14, Node 24.22.1, PySide6-Essentials/shiboken6 6.8.3. 상세 stdout/stderr는 `.local-reports/20261112-ci-refresh/` 및 `.local-reports/20261112-ci-restored-focused/` 로컬 전용이며 Git에 넣지 않는다.

- `pytest tests/test_editable_runner_build.py tests/test_runner_ports.py tests/test_setup_runtime.py tests/test_windows_runner_bundle.py -q`: 155 PASS/11 SKIP, exit 0.
- `pytest backend/gui_test/tests/test_board_connector.py backend/gui_test/tests/test_package.py tests/test_gui_test_layout.py -q`: 53 PASS, exit 0. 두 Qt offscreen 시험 포함.
- `bash scripts/build.sh all --skip-install` (venv PATH): 두 UI 빌드 PASS, exit 0.
- `package.py --stage-wheel`, `pip wheel --no-deps --no-build-isolation`: 각각 PASS. 실제 wheel의 모든 선언 package와 connector source byte 일치 PASS.
- Dashboard demo E2E 및 host-integration ZIP 생성: 각각 PASS, exit 0. 로컬 검증용이며 배포 게시 아님.
- 전체 `pytest -q`: 20 FAIL/1398 PASS/16 SKIP, exit 1 (`full.log`, `full.xml`). 실패는 cloud `/tmp/.git` marker를 실제/손상 저장소로 탐지하는 기존 source fixture 20건이다. 알려진 CI 9개 실패 항목은 모두 통과했지만 전체 성공이라고 표시하지 않는다.
- `python docs/testing/validate_docs.py`: PASS, exit 0 (`docs.log`).
- 독립 정적 코드 리뷰 APPROVED; reviewer는 제품 시험을 별도로 실행하지 않았다.

## 검증 경계

Windows 전체 회귀와 offline Windows 설치는 이 cloud에서 NOT_RUN이며 게시 승인 후 GitHub에서 확인해야 한다. 기존 source fixture는 cloud `/tmp/.git` marker로 차단될 수 있으며 이를 피하려고 제품 보안 검사를 완화하지 않는다. 실제 회사·SSH·COM·보드·TC·Jira 인수는 NOT_RUN이다. 새 EXE/릴리스/알림 설정 변경이나 DB migration 없음.

설치형 desktop connector의 실제 동작은 별도 미검증이다. 현재 upstream settings/supervisor는 `scripts.setup_runtime` 및 `backend.gui_test.connector.supervisor`를 참조한다. wheel 파일 포함/빌드 성공은 이 경로의 독립 설치 실행 검증을 뜻하지 않는다.

## PR #19 GitHub 검증 후속

`f0453860` 게시 후 [회귀 run 43321234159](https://github.com/graycoral/bsp_os_upgrade_dashboard/actions/runs/43321234159)의 Linux 결과는 1416 PASS/16 SKIP/2 FAIL이다. 남은 두 Qt 시험은 Python 의존성 설치 후 `libEGL.so.1` 누락으로 실패했다. Ubuntu job에 배포판 `libegl1` 설치를 추가하여 offscreen Qt의 시스템 의존성을 명시한다. 기존 실패 이력과 모든 시험은 유지한다. 이 변경의 GitHub 재검증은 게시 후 확인하며 성공 전 병합하지 않는다.
