# 빌드·실행 스크립트

웹 화면 빌드에는 Node.js 22.12 이상과 npm이 필요하다. 기본은 잠금 파일 기준 `npm ci` 후 Dashboard와 GUI Test 단독 화면을 모두 빌드한다. Python 서버·장비·TC는 시작하지 않는다.

| 환경 | 명령 |
|---|---|
| Windows PowerShell | `.\scripts\build.ps1` |
| Windows CMD | `scripts\build.cmd` |
| Linux/macOS Bash | `bash scripts/build.sh` |
| Dashboard만 | `.\scripts\build.ps1 -Target dashboard` / `bash scripts/build.sh dashboard` |
| 단독 GUI 화면만 | `.\scripts\build.ps1 -Target gui-test` / `bash scripts/build.sh gui-test` |
| 설치된 의존성 재사용 | PowerShell `-SkipInstall` / Bash `--skip-install` |

산출물: Dashboard `apps/web/dist`, 단독 GUI `gui_test/static`. 다른 현재 디렉터리에서도 스크립트 절대 경로로 호출할 수 있다. 실패는 비정상 종료하며 성공 메시지를 출력하지 않는다.

Windows 오프라인 ZIP/wheel 빌드는 기존 `gui_test/standalone/build.ps1`을 사용한다. Python3.12 x64와 Node22.12+의 22.x가 필요하며 [전용 가이드](../docs/gui_test/WINDOWS_BUILD.md)를 따른다.

- Linux 전체 Dashboard 실행: `bash scripts/start.sh` (API와 worker).
- Windows에서 Dashboard 접속: `connect-windows.ps1` 또는 SSH 터널.
- Windows 공유 TC 실행기: `start-windows-runner.ps1`. [Linux Dashboard + Windows 실행기 안내](../docs/gui_test/WINDOWS_RUNNER.md)의 설정/역방향 터널 준비 후 사용한다.

GUI Test UI를 빌드한 것과 실제 TC/보드 연결 설정은 별개다. 설정이 없는 기존 실행은 Mock다.
