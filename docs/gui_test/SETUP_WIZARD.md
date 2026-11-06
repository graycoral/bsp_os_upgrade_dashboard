# 실제 연결 설정 마법사

Windows 포터블 배포본은 [EXE 사용 안내](WINDOWS_RUNNER_PORTABLE.md)를 따른다. 기존 설정과 runtime을 재사용하며 Runner용 의존성 설치 단계는 생략한다. 아래 내용은 기존 소스 설치 경로다.

RQ-48 / D-49. 명령과 JSON을 하나씩 작성하는 대신 다음 스크립트를 실행한다. Python 3.11 이상이 필요하며 Linux 웹 빌드에는 Node.js 22.12 이상과 npm, Windows 연결에는 OpenSSH 클라이언트가 필요하다. 운영체제 패키지·SSH 서버 정책·회사 TC 의존성을 임의 설치/변경하지 않는다.

Linux 저장소 루트:

```bash
bash scripts/setup.sh
```

Windows 저장소 루트에서 Python Launcher for Windows(`py.exe`)가 설치된 상태로 `scripts\setup.cmd`를 실행하거나 탐색기에서 더블클릭한다. `py -3`로 설치된 Python 3을 선택하며 마법사가 요구하는 최소 버전은 3.11이다. Windows 진입점은 옆에 있는 Python/PowerShell 파일의 절대 경로를 바로 호출한다. 드라이브 전환이나 UNC 주소 추정·재연결은 하지 않는다. 공유 폴더에 접근 가능한 동일한 Windows 사용자로 실행해야 한다. PowerShell에서는 `./scripts/setup.ps1`도 사용할 수 있다. 두 PC는 같은 버전의 저장소를 사용한다. 스크립트는 브랜치를 바꾸거나 저장소를 자동 갱신하지 않는다. Windows 단독 Mock 화면(8767)을 실행하는 스크립트가 아니다.

## 메뉴

| 메뉴 | 동작 |
|---|---|
| 1 연결 설정 / 변경 | Windows는 TC 공유 경로·TC Python·보드/COM/노드·제한 시간·Linux SSH 서버/계정을 입력한다. Linux는 실제 실행기 연결을 설정한다. 저장 전 내용을 확인한다. |
| 2 의존성 설치 + 빌드 | 전용 Python 가상환경을 만들고 잠금 파일의 의존성을 설치한다. Linux는 웹 화면도 빌드한다. 기존 가상환경은 재사용한다. |
| 3 저장한 설정으로 실행 | 경로/보드/토큰을 다시 묻지 않는다. Linux는 API와 worker, Windows는 실행기와 SSH 양방향 터널을 함께 관리한다. |
| 4 연결 점검 | 인증·실행기 identity·COM 목록·TC catalog를 조회한다. TC, 콘솔, fastboot, 배치를 실행하지 않는다. |
| 5 인증 토큰 변경 / 확인 | 저장한 토큰을 명시적으로 표시하거나 교체한다. 일반 메뉴·설정 출력에는 토큰을 표시하지 않는다. |
| 6 이미지 자동 퓨징 설정 | Windows 콘솔/배치/이미지 프로파일과 Linux 모듈/사례/TC 매핑을 각각 설정하거나 비활성화한다. |
| 7 manifest 생성 (Linux) | 빌드 이미지 폴더와 배치를 입력받아 파일 해시 manifest를 만든다. 기존 manifest는 덮어쓰지 않는다. |
| 8 TC 목록 읽기 제한시간 설정 (갱신한 소스 마법사) | 기본100초, 1~600초 정수를 해당 PC runtime의 전용 파일에 저장한다. 다음 목록 조회부터 적용한다. |
| 0 종료 | 설정과 실행 이력은 보존한다. |

처음에는 Windows에서 1번으로 경로·보드를 입력하고 토큰을 생성한다. 생성한 토큰을 Linux의 1번에서 한 번 입력한다. 각 PC에서 2번을 완료하고 Linux 3번 → Windows 3번 순서로 실행한다. 이후에는 **각 PC에서 스크립트를 열고 3번만 선택**한다. Windows 브라우저에서 **http://127.0.0.1:8766** → Test 현황의 `WINDOWS RUNNER`/`shared`를 확인하고 실행 프로파일 저장 → Preflight → 테스트 시작을 진행한다.

연결·토큰·퓨징 설정 변경은 1/5/6번에서 한다. 기존 값은 입력 기본값으로 표시하며 Enter로 유지한다. 선택 노드명은 `-`로 비울 수 있다. 저장 확인에서 거절하거나 입력 중 Ctrl+C를 누르면 해당 편집은 저장하지 않는다. 이 연결 설정은 시작 시 읽으므로 실행 중에는 다른 스크립트 창에서 변경한 뒤 기존 서비스를 정상 종료하고 재실행한다. 목록 읽기 제한시간(8번/웹 설정)은 다음 요청부터 반영된다. JSON의 metadata/parser/추가 필드와 다른 퓨징 프로파일/모듈은 보존한다. 등록에서 삭제한 보드의 선택 프로파일 내 콘솔 매핑은 저장 미리보기에 제거를 표시한다.

Dual은 폴더 경로에 `dual`이 포함된 TC로 분류한다. 실제 노드명은 COM에서 추정하지 않는다. TC 기본 제한 시간은10초이며 1번에서 TC별 시간을 추가할 수 있다. 기존 parser/선행 TC 설정은 보존한다. 출력 판정과 source snapshot 제한은 [Windows 실행기 안내](WINDOWS_RUNNER.md)를 따른다.

## TC 목록 읽기가 오래 걸릴 때 · RQ-58

웹의 **소스 설정 → TC 목록 읽기 제한시간(초)**에서 값을 저장한다. 카탈로그가 실패했거나 연결되지 않은 상태에서도 저장할 수 있다. 기본은100초, 범위는1~600초 정수다. Linux의 저장 위치는 현재 서버 runtime의 `gui-test-settings.json`이며 마법사 기본 경로는 `<저장소>/.runtime/gui-test-settings.json`이다. API와 worker가 같은 runtime을 사용하면 재시작 없이 다음 조회부터 값을 읽는다. 진행 중 조회는 시작 시 값을 유지한다. 소스 선택·버전과 기존 Run은 변경하지 않는다.

갱신된 소스 마법사에서는 메뉴8로 같은 값을 저장한다. Linux 메뉴8은 웹/API와 같은 기본 파일을 사용하고 Windows 메뉴8은 `%USERPROFILE%\.bsp-dashboard\windows\runtime\gui-test-settings.json`을 사용한다. Windows의 값은 그 PC 마법사의 로컬 점검용이며 Linux 웹 설정을 바꾸지 않는다. 사용자 지정 서버 runtime을 쓴다면 해당 서버 파일과 기본 `.runtime`을 구분해야 한다.

이번 소스 마법사 점검만 임시로 바꾸려면 `py -3 -X utf8 scripts/setup_runtime.py --catalog-timeout 180`(Windows) 또는 `python3 scripts/setup_runtime.py --catalog-timeout 180`(Linux)을 실행한다. 이 인자는 파일을 자동 변경하지 않으며 메뉴4의 TC 목록 요청에만 적용된다. 인증·보드 조회는 기존5초이고 실제 TC 실행 제한시간과도 별개다.

메뉴4는 설정·토큰 준비 → 실행기 인증 확인 → 보드 목록 조회 → `TC 목록을 읽는 중… (최대 N초)`를 각 호출 전에 즉시 출력한다. 실패 메시지는 어느 단계에서 멈췄는지 표시하며 토큰이나 인증 응답 본문을 출력하지 않는다. 목록 timeout은 기다린 값과 조정 안내를 제공하고 인증 거부·일반 연결 오류와 구분한다.

**이미 승인된 Runner ZIP/EXE는 이번 작업에서 교체하지 않는다.** 기존 EXE는 Linux 대시보드의 새 목록 대기 설정과 호환되지만 그 EXE 자체의 메뉴4는 이전5초 동작을 유지한다. 새 진행 표시·메뉴8·CLI 옵션은 갱신된 소스 마법사에만 있다. EXE의 새 `source_snapshot_v1` capability를 의미하지 않는다. 실제 공유 폴더·SSH·장비 인수는 [실행 기록](../testing/runs/20261106-catalog-timeout.md)에 별도로 관리한다.

## 저장과 인증

- Windows: `%USERPROFILE%\.bsp-dashboard\windows\windows-runner.json`. `_setup`에 SSH 선택을 함께 저장하여 보드 설정과 한 번에 교체한다. 실행 기록은 같은 폴더의 `runtime`, 실행기 가상환경은 `venv`다. TC는 별도로 등록한 기존 Windows Python을 사용한다.
- Linux: 저장소 `.runtime/gui-test.json`, `.runtime/device-test.json`. 토큰은 저장소 밖 `~/.bsp-dashboard/linux/runner-token`에 소유자 전용 폴더700/파일600으로 저장한다.
- Windows 토큰은 `runner-token.dpapi`에 현재 Windows 사용자 DPAPI로 암호화한다. 다른 계정/PC로 파일을 복사해 공유할 수 없다. 양쪽에 동일한 토큰 문자열을 처음 한 번 등록한다. 서비스 환경변수로만 전달하며 SSH 자식에는 전달하지 않는다. 교체 시 양쪽을 맞추고 재시작한다.
- 일반 JSON 저장은 임시 파일을 쓴 뒤 교체하며 기존 파일은 이름이 겹치지 않는 `.bak`으로 남긴다. DB·과거 Mock 기록·실행 snapshot을 삭제/변환하지 않는다.
- 개인 경로를 바꾸려면 Linux `bash scripts/setup.sh --home /개인/설정폴더`, Windows CMD `scripts\setup.cmd --home C:\개인\설정폴더`로 같은 경로를 계속 지정한다. 토큰 폴더는 저장소 밖이어야 한다.

SSH 인증은 OpenSSH가 담당한다. SSH 키/agent가 준비되면 재접속 때 암호를 다시 입력하지 않는다. 암호 인증만 사용하는 서버는 SSH 암호를 물을 수 있다. 마법사는 SSH 암호를 저장하거나 호스트 키 검증을 해제하지 않는다. 서버는 포트 포워딩을 허용해야 한다. 기본 loopback 포트는 Dashboard8766/실행기8771이며 CLI 인자로 변경할 수 있다. 충돌하면 기존 서비스를 임의 종료하지 않는다.

Windows 소스 실행 예시는 `py -3 -X utf8 scripts/setup_runtime.py --port 18771 --dashboard-port 18766`이다. `--port`(`--runner-port`)를 생략하면8771이며 Windows Runner만 바꾼다. Linux 역방향 포트는 기본8771을 유지하므로 이 예시에서는 Linux 설정을 바꿀 필요가 없다. Windows 브라우저는 `http://127.0.0.1:18766`을 사용한다. `scripts\setup.cmd`도 같은 인자를 전달한다.

Linux 포트가 겹치면 양쪽 실행에 같은 `--remote-runner-port`와 `--remote-dashboard-port`를 지정한다. Linux 예시: `bash scripts/setup.sh --remote-runner-port 28771 --remote-dashboard-port 28766`. 최초에는 메뉴1에서 새 실행기 URL을 확인·저장하고 메뉴3을 실행한다. Linux의 `--port`/`--dashboard-port`는 Windows 쪽 의미를 유지하며 Linux API를 바꾸려면 `--remote-dashboard-port`를 사용한다. `--ssh-port`는 이번 Windows 실행에만 저장된 SSH 포트보다 우선한다. 인자는 자동 저장되지 않으며 메뉴1에서 명시적으로 저장하는 연결 URL 외 기존 설정·토큰·이력은 보존한다. 전체 옵션 표와 양쪽 명령은 [포터블 Runner 포트 안내](WINDOWS_RUNNER_PORTABLE.md#포트가-겹칠-때)를 따른다.

## 시작·종료·실패

잘못된 설정·토큰·설치 실패를 Mock로 대체하지 않는다. Windows 실행기/SSH 중 하나가 종료되면 나머지 자식을 정리한다. Linux도 API/worker 중 하나가 종료되면 다른 자식을 정상 종료한다. Ctrl+C는 스크립트가 시작한 자식의 정상 종료를 기다린 뒤 메뉴로 돌아간다. 진행 중 퓨징/TC/BSP 작업의 대기가 길어질 수 있으며 실행기를 강제 종료하지 않는다. 강제 창 닫기/OS 종료 후에는 기존 실행 불명/예약 복구 계약을 따른다.

Windows 로그는 `runtime/setup-runner.log`다. 이전 수동 실행기와 마법사는 기본 runtime이 다르다. **진행 중/UNKNOWN 실행을 새 runtime으로 우회하지 말고 기존 실행을 먼저 복구**한다. 같은 사용자 홈에서는 같은 runtime을 재사용한다. 기존 대기 작업이 있는 runtime에서 서비스를 시작하면 기존 실행 정책에 따라 재개할 수 있다.

## 이미지와 BSP 설정

Windows 6번에서 이미지 루트, fastboot 경로, 검토한 배치, 성공/실패 문구, COM별 baud/개행/lkshell 프롬프트/부팅 문구/fastboot serial을 입력한다. 배치는 실행하지 않고 SHA256만 계산한다. 실제 값과 배치 검토 확인 후에만 활성화한다.

Windows 실행기와 터널을 켠 후 Linux의 별도 마법사 창에서 6번을 선택한다. 제공된 보드/TC 목록에서 선택하고 정확한 BSP 모듈 이름·프로파일·이미지 상대 폴더·필수 사례별 TC 순서를 저장한다. 선행 TC/Single·Dual 조건을 검사한다. 최상위 자동 설정이 꺼져 있을 때 다른 기존 활성 모듈까지 함께 켜지면 목록을 추가 확인한다. 재시작 후 준비된 대기 작업에도 퓨징이 배정될 수 있음을 활성화 전에 알린다.

Linux 7번에서 만든 manifest를 BSP 빌드 산출물 경로에 등록한다. 빌드마다 생성하려면 [기존 생성기](../../scripts/create_flash_manifest.py)를 프로젝트 빌드 명령에 연결한다. 프로젝트별 빌드 스크립트는 자동 수정하지 않는다. 배치 제약과 지원 범위는 [자동 퓨징 계약](../design/AUTOMATIC_FLASH_TEST.md)을 따른다.

**TC 연결과 BSP 실행 모드는 별개다.** BSP도 실제로 실행하려면 웹의 환경 설정에서 실제 Linux 실행·작업 폴더·소스·도구·빌드/검증 명령을 지정한다. 새 작업부터 적용되며 기존 demo Job을 실제 Job으로 변환하지 않는다. 실제 Linux/SSH/보드 인수는 T-141 및 기존 T-130/T-136이며 모의 자동 시험과 구분한다.


## Windows 배치 진입 오류 시 직접 실행

회사 환경에서 파일 읽기와 CMD의 Z: 조회는 성공하지만 배치 진입에 드라이브 오류가 보고됐다. 사용자가 scripts 폴더에서 다음 명령으로 마법사가 실행됨을 확인했다.

```powershell
py -3 -X utf8 .\setup_runtime.py
```

저장소 루트에서는 `py -3 -X utf8 scripts/setup_runtime.py`로 실행한다. setup.cmd/setup.ps1도 같은 Python Launcher와 스크립트 절대 경로를 사용한다. setup.ps1의 명시적인 `-PythonExecutable` 지정은 유지한다. build.cmd는 build.ps1의 절대 경로를 호출한다. 이 변경만으로 실제 공유 폴더의 npm 빌드 성공을 검증한 것은 아니다.

이전 버전이 생성한 `%LOCALAPPDATA%\bsp-dashboard\setup-share.txt`는 새 진입점에서 사용하지 않는다. 최초 오류가 CMD 시작 설정인지 다른 환경 문제인지는 아직 확인되지 않았으며, 경로 재연결 코드를 추가한 이전 시도로 해결됐다고 보지 않는다. [회귀 검증 기록](../testing/runs/20261103-direct-windows-launch.md).


## 실행기 설치 전 Test 현황 보기

업데이트한 대시보드에서 **Test 현황 → 실제 연결 모드로 전환**을 선택한다. 브라우저가 선택을 기억한다. Windows 패키지 추가 설치 없이 상태 화면을 볼 수 있으며 미설정/미연결에서는 TC·보드가 빈 목록이다. 실행하려면 설정 마법사로 연결을 저장하고 실행기·SSH를 준비한다. Linux API와 worker를 재시작한 후 ‘연결 다시 확인’을 누른다. 기존 보기의 Mock 기록은 보존된다. 이 기능은 대시보드 코드/화면 빌드 업데이트가 필요하며 이미 설치된 Windows 패키지를 자동 재사용하는 설치 옵션은 아니다.
