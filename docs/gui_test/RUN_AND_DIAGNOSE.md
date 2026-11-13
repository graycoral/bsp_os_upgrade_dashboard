# 실행과 연결 진단 안내

Windows GUI 사용자는 저장소 루트의 `board-connector.cmd` 하나를 실행한다. 설치 확인·패키지 준비·GUI 시작을 자동 처리한다. 아래 CLI는 기존 자동화와 진단용이다. [GUI 가이드](TEST_BOARD_CONNECTOR_GUI.md).

보드 커넥터 GUI는 [설치·사용·연동 가이드](TEST_BOARD_CONNECTOR_GUI.md)를 따른다. 아래는 기존 CLI 실행·배포 안내다.

편집 가능한 Runner는 [전용 안내](WINDOWS_RUNNER_EDITABLE.md)의 `launch.cmd`와 `diagnose.cmd`를 사용한다. 아래 18771/18766 및 원격 8765는 특정 구성 예시이며 전역 기본값이 아니다. 기본 로컬 Runner/브라우저와 원격 Runner/API는 각각 8771/8766이다. CLI > 저장값 > 기본값이며 자동 저장하지 않는다. 로컬 충돌 시 실제 URL은 실행 화면에서 확인하고 원격 비기본 포트는 최초 명시 설정한다.

기존 연결 설정은 재사용한다. 현재 소스는 연결 토큰을 요구하지 않는다. 구형 EXE 안내는 당시 배포물 기준이다. 연결 설정이 없으면 인자 없이 EXE 또는 setup을 열어 메뉴 1에서 설정한다. 소스 설치는 메뉴 2의 의존성 설치·빌드도 수행한다. 기존 설정이 있으면 이 단계를 생략한다. 기존에 사용자 지정 `--home`을 사용했다면 새 기본 경로를 만들지 말고 모든 ports/run/doctor 명령에 기존 `--home` 경로를 계속 지정한다. 실제 회사 환경 인수는 별도다.

## 포트와 최초 준비

| 위치 | 용도 | 포트 |
|---|---|---|
| Linux | 회사 대시보드 | 8765 |
| Windows | 브라우저에서 접속할 터널 | 18766 |
| Windows | Runner | 18771 |
| Linux | Windows Runner로 향하는 역방향 터널 | 8771 |

각 PC에서 한 번 포트를 저장한 뒤 일상 실행에 재사용한다.

```bash
bash scripts/setup.sh ports --remote-dashboard-port 8765 --remote-runner-port 8771 --save
```

```powershell
.\BSP-Windows-Runner.exe ports --port 18771 --dashboard-port 18766 --remote-dashboard-port 8765 --remote-runner-port 8771 --save
```

`ports`만 실행하면 현재 유효한 값과 출처를 표시한다. 명시한 `--save`만 저장하며 CLI 값이 저장값보다 우선한다. Linux 프로파일은 `<저장소>/.runtime/setup-ports.json`, Windows는 `<선택한 home>/setup-ports.json`이다. 기존 연결과 토큰은 변경하지 않는다. Windows 포터블 ZIP 전체를 `C:\BSP-Runner` 같은 로컬 폴더에 풀고 동봉 파일을 함께 둔다. Z:의 EXE만 실행하지 않는다. TC와 이미지가 공유 폴더에 있는 구성은 유지한다.

## 매일 실행

Linux 저장소에서 `bash scripts/setup.sh run` 또는 `bash scripts/run.sh`를 먼저 실행하고 Windows에서 `.\BSP-Windows-Runner.exe run` 또는 `.\launch-run.cmd`로 Runner와 SSH 터널을 실행한다. 소스 설치 Windows에서는 `.\scripts\setup.cmd run`을 사용한다. 두 창을 유지한 상태에서 Windows 브라우저로 `http://127.0.0.1:18766`을 연다. 소스 설치는 각 PC의 갱신된 마법사, 포터블 설치는 검증된 새 ZIP의 실행 명령을 사용한다. 기본 메뉴도 유지된다. 이 명령은 `launch-run.cmd`와 `diagnose.cmd`가 포함된 새 배포본에서 지원한다. 이전 ZIP은 자동 갱신되지 않는다.

## 연결 진단

별도 창에서 Linux는 `bash scripts/setup.sh doctor` 또는 `bash scripts/doctor.sh`, Windows는 `.\BSP-Windows-Runner.exe doctor` 또는 `.\diagnose.cmd`를 실행한다. 소스 Windows는 `.\scripts\setup.cmd doctor`를 사용한다. Windows 로컬 진단은 Windows Runner와 공유 경로를 점검하며, Linux 측 진단은 Linux 역방향 경로를 확인한다. `doctor --only catalog`은 목록 단계만 선택한다. 설정·인증·보드·목록 단계의 성공과 실패, 목록 timeout을 구분한다. 진단은 TC 실행이나 퓨징을 하지 않는다. 서버가 목록을 읽는 동안 임시 catalog snapshot을 만들 수 있으며 그 외 설정 변경은 하지 않는다.

목록 읽기 기본 제한은 100초다. 웹 설정 또는 갱신된 마법사 메뉴 8에서 영속 값을 바꿀 수 있으며 CLI override는 해당 진단에만 적용된다. 실제 회사 SSH·공유 폴더·장비 인수는 별도다.

인자를 생략한 setup 진입점은 기존 메뉴를 연다. `--only identity`, `--only boards`, `--only catalog`은 doctor 전용이며 `--save`는 ports 전용이다. `--catalog-timeout 180`은 해당 진단의 목록 요청에만 적용한다. timeout은 전송 제한이며 진단 전체의 절대 마감시간이 아니다. 래퍼는 인자가 없어도 종료 대기를 추가하지 않고 실제 종료 코드를 전달한다.

### 단계별 빠른 진단

별도 Windows 창에서 다음 순서로 실행한다. Linux도 `bash scripts/setup.sh` 뒤에 같은 인자를 붙여 각각 실행한다.

```powershell
.\BSP-Windows-Runner.exe doctor --only identity
.\BSP-Windows-Runner.exe doctor --only boards
.\BSP-Windows-Runner.exe doctor --only catalog
```

Windows 로컬이 SUCCESS이고 Linux가 실패하면 SSH 역방향 터널과 Linux 접근 경로를 확인한다. catalog가 TIMEOUT이면 다음 명령으로 이번 요청만 180초로 점검한다.

```powershell
.\BSP-Windows-Runner.exe doctor --only catalog --catalog-timeout 180
```

이미 실행 중이면 `run`을 중복 실행하지 않고 별도 창에서 `doctor`를 사용한다. 포트 설정을 변경한 뒤에는 기존 창에서 Ctrl+C로 정상 종료하고 다시 `run`한다. 기존에 지정한 `--home` 경로는 계속 유지한다.
