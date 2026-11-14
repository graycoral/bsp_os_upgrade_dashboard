# 빌드·실행 스크립트

편집 가능한 Runner는 `scripts\build-connector-bundle.cmd` 한 명령으로 빌드하며 오프라인 입력 캐시는 `-Offline -CachePath <경로>`를 사용한다. 회사 PC에서 소스 편집 후 재시작하거나 `repack.cmd`로 재포장한다. [상세 안내](../docs/gui_test/WINDOWS_RUNNER_EDITABLE.md). 로컬 검증을 완료했고 실제 회사 인수는 별도다.

RQ-59의 직접 실행·진단·포트 저장은 [실행과 진단 안내](../docs/gui_test/RUN_AND_DIAGNOSE.md)를 따른다. 새 ZIP은 빌드·로컬 검증됐다. 아래 기존 ZIP 설명은 해당 기존 배포본의 이력이다.

자동 조정/v2는 새 작업 opt-in이며 기본 OFF다. 등록 명령의 구조화 결과 파일·환경 변수와 BSP schema1 이전 전 읽기 전용 백업 API는 [도입/복구 안내](../docs/agents/ORCHESTRATION_V2_OPERATIONS.md)를 따른다. 수동 `scripts/claude_orchestrator.py`는 사용자 직접 호출용 오프라인 검사 도구로 유지하며 자동 worker를 시작하지 않는다.

TEST BOARD CONNECTOR는 [편집형 소스 배포 안내](../docs/gui_test/WINDOWS_RUNNER_EDITABLE.md)를 따른다. 2026-11-12부터 새 EXE는 만들지 않으며 기존 EXE ZIP·체크섬은 저장소에서 제거했다. 2026-11-14에는 EXE 전용 builder·spec·build lock도 제거했다. frozen runtime 호환과 과거 회귀 시험은 보존한다. 웹 재빌드는 Runner 재설치를 요구하지 않는다. 공개 Python·OpenSSH·platform-tools는 설치 단계에서 검사·준비하며 회사 TC 패키지·드라이버는 제공된 서명/해시 입력만 사용한다.

Windows 사용자 진입점은 저장소 루트의 **`board-connector.cmd`**다. Python 3.13 64비트를 우선 선택하고 설치 확인·GUI 실행을 한 번에 처리한다. 3.11/3.12도 호환된다. Linux 설정과 기존 CLI 자동화에는 `scripts/setup.*`를 유지한다. [설정 마법사 안내](../docs/gui_test/SETUP_WIZARD.md).

보드 커넥터의 기본은 Windows 로컬 **브라우저 화면**이며 Qt 설치/import 없이 core 환경을 준비한다. `--ui qt`일 때만 기존 Qt 호환 환경을 준비한다. `--diagnose`는 설치·GUI·Manager·SSH·COM 실행 없는 진단이다. BC 코드·로그·직접 성공한 Python 지정 방법은 [가이드](../docs/gui_test/TEST_BOARD_CONNECTOR_GUI.md#cmd-경로-오류--번호별-진단과-조치)를 따른다. 이 화면의 고정 ES module/CSS는 npm 빌드 없이 source/wheel/bundle에 포함한다. 아래 Node 빌드 명령은 Agent Monitor/GUI Test 단독 앱의 별도 빌드다.

개발용 웹 커넥터 회귀는 `python scripts/test_connector_browser.py`다. 설치된 Playwright/Chromium으로 새 모의 서버만 사용하며 회사 서비스/보드에 연결하지 않는다. 실사용 Mac/Linux 미리보기는 `python -m backend.gui_test.connector --preview`이며 모의 프로파일을 임시 폴더에 격리한다.

웹 화면 빌드에는 Node.js 22.12 이상과 npm이 필요하다. 기본은 잠금 파일 기준 `npm ci` 후 Dashboard와 GUI Test 단독 화면을 모두 빌드한다. Python 서버·장비·TC는 시작하지 않는다.

| 환경 | 명령 |
|---|---|
| Windows PowerShell | `.\scripts\build-ui.cmd` |
| Windows CMD | `scripts\build-ui.cmd` |
| Linux/macOS Bash | `bash scripts/build-ui.sh` |
| Dashboard만 | `.\scripts\build-ui.cmd -Target dashboard` / `bash scripts/build-ui.sh dashboard` |
| 단독 GUI 화면만 | `.\scripts\build-ui.cmd -Target gui-test` / `bash scripts/build-ui.sh gui-test` |
| 설치된 의존성 재사용 | PowerShell `-SkipInstall` / Bash `--skip-install` |

산출물: Dashboard `apps/web/dist`, 단독 GUI `apps/gui-test/static`. 다른 현재 디렉터리에서도 스크립트 절대 경로로 호출할 수 있다. 실패는 비정상 종료하며 성공 메시지를 출력하지 않는다.

`build-ui.cmd`는 해당 자식 PowerShell 프로세스에만 `-ExecutionPolicy Bypass`를 적용한다. 사용자/컴퓨터 실행 정책을 저장하거나 변경하지 않으며 관리자 실행은 필요하지 않다. `.ps1` 직접 호출이 실행 정책으로 차단되면 위 CMD 진입점을 사용한다. 회사 그룹 정책(MachinePolicy/UserPolicy)이 설정되어 있으면 이 옵션보다 우선하므로 관리자에게 정책 확인이 필요하다. [Microsoft 실행 정책 설명](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/about/about_execution_policies?view=powershell-5.1).

PowerShell 7에서 CMD를 거쳐 실행해도 Windows PowerShell 기본 모듈을 사용하도록, 배치의 `setlocal` 범위에서 상속된 `PSModulePath`를 비운다. 빌드는 표준 모듈만 사용하며 부모 셸·저장된 환경 변수는 바꾸지 않는다. [Microsoft의 버전 간 모듈 경로 설명](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/about/about_psmodulepath?view=powershell-7.3).

Windows 오프라인 ZIP/wheel 빌드는 기존 `apps/gui-test/build-windows-package.ps1`을 사용한다. Python3.12 x64와 Node22.12+의 22.x가 필요하며 [전용 가이드](../docs/gui_test/WINDOWS_BUILD.md)를 따른다.

독립 소스 내보내기는 `python apps/gui-test/package.py --standalone`으로 수행한다. `apps/gui-test/`, `backend/gui_test/`, `packages/gui-test-ui/src/`와 최소 `backend/__init__.py`의 상대 위치를 유지한다. `apps/web`·Git 이력 없이 빌드할 수 있으며 단독 앱 폴더만 복사하는 계약을 대체한다. UI 전용 명령은 `npm ci --prefix apps/gui-test`, `npm run build --prefix apps/gui-test`다.

소스 서비스는 `python apps/gui-test/launch.py start`로 시작한다. wheel 제작은 `python apps/gui-test/package.py --stage-wheel <stage-dir>` 뒤 `python -m pip wheel --no-deps --no-build-isolation --wheel-dir <wheel-dir> <stage-dir>`를 사용한다. 소스 import `backend.gui_test.*`와 설치 import `gui_test.*`를 구분하며 설치 CLI `gui-test`/`gui-test-runner`는 유지한다. [구조 계약](../docs/design/GUI_TEST_LAYOUT.md).

- Linux 전체 Dashboard 실행: `bash run.sh` (공통 서비스 관리자의 API와 worker).
- Windows 보드 연결·Dashboard 열기: `board-connector.cmd`. [보드 커넥터 안내](../docs/gui_test/TEST_BOARD_CONNECTOR_GUI.md).

GUI Test UI를 빌드한 것과 실제 TC/보드 연결 설정은 별개다. 설정이 없는 기존 실행은 Mock다.

자동 퓨징용 빌드 manifest는 저장소 루트에서 `python -m scripts.create_flash_manifest --root <이미지폴더> --batch <상대배치파일> --output <폴더밖새JSON>`으로 생성한다. 파일 해시만 계산하며 보드를 실행하지 않는다. [설정·실행 계약](../docs/design/AUTOMATIC_FLASH_TEST.md)을 따른다.

## Windows 실행 스크립트 정리 · 2026-11-13

| 처리 | 파일 | 역할 |
|---|---|---|
| 단일 사용자 진입점 | `board-connector.cmd` | Python 탐색 후 공통 준비 코드 호출 |
| 공통 구현 | `scripts/board_connector.py` | 환경 검사·조건부 설치·오류 기록·GUI 실행 |
| 제거 | `apps/board-connector/launch.cmd` | 설치를 처리하지 못하던 별도 GUI 진입점 |
| 제거 | `scripts/start-windows-runner.ps1`, `scripts/connect-windows.ps1` | GUI 관리자가 함께 담당하는 Host·SSH 수동 실행 |
| 유지 | `scripts/setup.*` | 공통 `run`, `doctor`, `ports` 하위 명령. Python 실행 로직은 setup_runtime.py에만 있음 |
| 유지 | `apps/gui-test/launch.py start` | 별도 GUI Test 웹 서비스 시작. 보드 커넥터 GUI와 다른 제품 진입점 |
| 유지 | `build-ui.*`, `build-connector-bundle.*` | 각각 UI 빌드/편집형 소스 조립. 사용자 커넥터 실행에 필요 없음 |

이 실행기는 공개 Python·OpenSSH client·platform-tools를 누락 시 준비한다. 회사 TC 패키지와 드라이버는 이름을 추정하지 않으며, 공급된 서명/해시 검증 파일을 별도 설치 입력으로 받는다. 회사 pip 설정과 `PIP_NO_INDEX`/`PIP_FIND_LINKS`를 사용할 수 있다. 실행 중 환경은 덮어쓰지 않고 새 환경 준비 실패 시 이전 환경·설정을 유지한다. 패키지 설치를 동시에 두 번 진행하지 않는다.


## 2026-11-14 명령 정리

| 역할 | 현재 명령 | 이전 경로 처리 |
|---|---|---|
| Agent Monitor 시작 | `bash run.sh [--port PORT]` | `scripts/start.sh` 제거; 기존 .runtime을 공통 서비스 관리자에 연결 |
| 설정·실행·진단 | `scripts/setup.sh` 또는 `scripts/setup.cmd`의 `run`, `doctor`, `ports` | `scripts/run.*`, `scripts/doctor.*` 별칭 제거 |
| 양 UI 빌드 | `scripts/build-ui.cmd` / `bash scripts/build-ui.sh` | `scripts/build.*`에서 명명 변경 |
| Windows standalone ZIP | `apps/gui-test/build-windows-package.cmd` | 앱 `build.cmd/ps1`에서 명명 변경 |
| 편집형 connector bundle | `scripts/build-connector-bundle.cmd` | `build-editable-runner.*` 및 Python `build_editable_runner.py`에서 명명 변경 |
| API만 실행 | `python scripts/serve_monitor.py` | `scripts/serve.py`에서 명명 변경 |
| BSP profile 관리 | `python scripts/manage_profile.py` | `scripts/configure.py`에서 명명 변경 |
| Dashboard 브라우저 시험 | `python scripts/test_dashboard_browser.py` | `scripts/test_e2e.py`에서 명명 변경 |
| standalone 웹 시작 | `python apps/gui-test/launch.py start` | 앱 `start.ps1` 별칭 제거 |
| standalone UI 빌드 | `npm run build --prefix apps/gui-test` | 형제 앱의 `build:gui-test` 별칭 제거 |

과거 고정 커밋·배포본·시험 기록의 명령은 당시 증거로 보존한다. 새 소스에는 현재 명령을 사용하며 설정/DB/runtime의 이전은 수행하지 않는다. 루트 `board-connector.cmd`와 설치형 `gui-test*` CLI 이름은 유지한다.


## 전체 Agent Monitor 설치·복사 전달

`python3 apps/agent-monitor/delivery.py --output <빈 폴더>`는 전체 서비스·화면 자산·커넥터 의존 소스·시험을 manifest와 함께 복사한다. UI는 먼저 `build-ui`로 빌드한다. `python3 apps/agent-monitor/manage.py start --port 8765`는 검증된 기존 설치를 재사용하고 없을 때 준비한다. `status`, `stop`, `install`도 같은 관리자에 있다. [설치·API·회사 adapter 안내](../docs/agents/PLUGIN_CONTROL_API.md).

Linux 설정 마법사의 `run`도 같은 관리자를 호출한다. 기존 저장소 `.runtime`을 보존하며 메뉴를 닫아도 서비스를 종료하지 않는다. 직접 관리자를 호출할 때 `--runtime`은 처음 한 번 기존 경로를 연결하는 옵션이고, 이후 경로는 고정한다.


## 공개 필수 도구·오프라인 이관·복원

- `scripts/bootstrap-prerequisites.sh`: 지원 Python이 없을 때 Linux 배포판 Python/venv·OpenSSH client 준비. 이미 지원 Python이 있으면 누락 SSH만 준비한다.
- `scripts/bootstrap-prerequisites.ps1`: Windows Python 3.13·OpenSSH client·Google platform-tools 준비. `-PythonOnly`, `-Plan`, 서명 MSI 및 offline hash-pinned requirements 입력을 제공한다. `board-connector.cmd --diagnose`는 이 설치를 호출하지 않는다.
- `python3 apps/agent-monitor/manage.py inspect-runtime`: 실행 관리자 잠금 아래 저장 계약·상태를 검사한다. DB 상태나 하드웨어를 바꾸지 않는다.
- `... manage.py adopt --release SHA256 --inspection-revision SHA256`: 최초의 호환 runtime 이관. 백업 후 설치 포인터만 연결하고 UNKNOWN·실행/예약·미지원 계약은 거부한다.
- `... manage.py rollback [--release SHA256]`: manifest·설치 환경 검증 후 직전/지정 release로 복원. 실행 소유권이나 미완료 기록이 있으면 거부한다.
- `... manage.py cleanup --keep 2 [--apply]`: 현재·직전·runtime 참조 release와 미검증 폴더를 보존하는 정리 계획/적용.
- `... manage.py tools [--apply]`: 공개 도구 준비 계획/적용. `--artifact-manifest`, `--artifact-signature`, `--trusted-keyring`, `--wheelhouse`는 회사가 제공한 승인 파일을 검증하는 입력이다.

정확한 명령과 공급 파일 계약은 [설치·공통 제어 안내](../docs/agents/PLUGIN_CONTROL_API.md)를 따른다. 공개 명령 생성·로컬 모의 시험과 실제 OS 설치·회사 드라이버/TC·장비 인수는 구분한다. 실제 설치/회사 인수는 별도 NOT_RUN이다.
