# 빌드·실행 스크립트

Windows Runner 포터블 ZIP은 `scripts/build_windows_runner.py`로 빌드한다. 회사 PC에서 Runner용 pip 설치 없이 EXE로 설정·실행하며 [전용 안내](../docs/gui_test/WINDOWS_RUNNER_PORTABLE.md)를 따른다. TC 전용 Python·패키지와 OpenSSH는 별도다.

실제 Linux Dashboard + Windows 보드 연결은 **Linux `bash scripts/setup.sh` / Windows `scripts\setup.cmd`**의 단계별 메뉴를 먼저 사용한다. 최초 입력을 저장하고 다음에는 3번 실행만 선택한다. 경로·보드·토큰·이미지 설정 변경과 설치/빌드/연결 점검을 제공한다. [설정 마법사 안내](../docs/gui_test/SETUP_WIZARD.md).

웹 화면 빌드에는 Node.js 22.12 이상과 npm이 필요하다. 기본은 잠금 파일 기준 `npm ci` 후 Dashboard와 GUI Test 단독 화면을 모두 빌드한다. Python 서버·장비·TC는 시작하지 않는다.

| 환경 | 명령 |
|---|---|
| Windows PowerShell | `.\scripts\build.cmd` |
| Windows CMD | `scripts\build.cmd` |
| Linux/macOS Bash | `bash scripts/build.sh` |
| Dashboard만 | `.\scripts\build.cmd -Target dashboard` / `bash scripts/build.sh dashboard` |
| 단독 GUI 화면만 | `.\scripts\build.cmd -Target gui-test` / `bash scripts/build.sh gui-test` |
| 설치된 의존성 재사용 | PowerShell `-SkipInstall` / Bash `--skip-install` |

산출물: Dashboard `apps/web/dist`, 단독 GUI `apps/gui-test/static`. 다른 현재 디렉터리에서도 스크립트 절대 경로로 호출할 수 있다. 실패는 비정상 종료하며 성공 메시지를 출력하지 않는다.

`build.cmd`는 해당 자식 PowerShell 프로세스에만 `-ExecutionPolicy Bypass`를 적용한다. 사용자/컴퓨터 실행 정책을 저장하거나 변경하지 않으며 관리자 실행은 필요하지 않다. `.ps1` 직접 호출이 실행 정책으로 차단되면 위 CMD 진입점을 사용한다. 회사 그룹 정책(MachinePolicy/UserPolicy)이 설정되어 있으면 이 옵션보다 우선하므로 관리자에게 정책 확인이 필요하다. [Microsoft 실행 정책 설명](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/about/about_execution_policies?view=powershell-5.1).

PowerShell 7에서 CMD를 거쳐 실행해도 Windows PowerShell 기본 모듈을 사용하도록, 배치의 `setlocal` 범위에서 상속된 `PSModulePath`를 비운다. 빌드는 표준 모듈만 사용하며 부모 셸·저장된 환경 변수는 바꾸지 않는다. [Microsoft의 버전 간 모듈 경로 설명](https://learn.microsoft.com/en-us/powershell/module/microsoft.powershell.core/about/about_psmodulepath?view=powershell-7.3).

Windows 오프라인 ZIP/wheel 빌드는 기존 `apps/gui-test/build.ps1`을 사용한다. Python3.12 x64와 Node22.12+의 22.x가 필요하며 [전용 가이드](../docs/gui_test/WINDOWS_BUILD.md)를 따른다.

독립 소스 내보내기는 `python apps/gui-test/package.py --standalone`으로 수행한다. `apps/gui-test/`, `backend/gui_test/`, `packages/gui-test-ui/src/`와 최소 `backend/__init__.py`의 상대 위치를 유지한다. `apps/web`·Git 이력 없이 빌드할 수 있으며 단독 앱 폴더만 복사하는 계약을 대체한다. UI 전용 명령은 `npm ci --prefix apps/gui-test`, `npm run build --prefix apps/gui-test`다. `apps/web`의 `build:gui-test`는 형제 앱에 위임하는 편의 명령이다.

소스 서비스는 `python apps/gui-test/launch.py start`로 시작한다. wheel 제작은 `python apps/gui-test/package.py --stage-wheel <stage-dir>` 뒤 `python -m pip wheel --no-deps --no-build-isolation --wheel-dir <wheel-dir> <stage-dir>`를 사용한다. 소스 import `backend.gui_test.*`와 설치 import `gui_test.*`를 구분하며 설치 CLI `gui-test`/`gui-test-runner`는 유지한다. [구조 계약](../docs/design/GUI_TEST_LAYOUT.md).

- Linux 전체 Dashboard 실행: `bash scripts/start.sh` (API와 worker).
- Windows에서 Dashboard 접속: `connect-windows.ps1` 또는 SSH 터널.
- Windows 공유 TC 실행기: `start-windows-runner.ps1`. [Linux Dashboard + Windows 실행기 안내](../docs/gui_test/WINDOWS_RUNNER.md)의 설정/역방향 터널 준비 후 사용한다.

GUI Test UI를 빌드한 것과 실제 TC/보드 연결 설정은 별개다. 설정이 없는 기존 실행은 Mock다.

자동 퓨징용 빌드 manifest는 저장소 루트에서 `python -m scripts.create_flash_manifest --root <이미지폴더> --batch <상대배치파일> --output <폴더밖새JSON>`으로 생성한다. 파일 해시만 계산하며 보드를 실행하지 않는다. [설정·실행 계약](../docs/design/AUTOMATIC_FLASH_TEST.md)을 따른다.
