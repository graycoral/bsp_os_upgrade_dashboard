# Windows Runner 실행파일 사용

> 이 문서의 기존 배포물 설명에는 이전 토큰 설정이 포함된다. 현재 소스는 연결 토큰을 사용하지 않으며 새 EXE/ZIP을 만들지 않는다. 현재 설치·연결은 [보드 커넥터 가이드](TEST_BOARD_CONNECTOR_GUI.md)를 따른다. 구형 바이너리의 동작은 바뀌지 않는다.

**과거 배포 이력**: 2026-11-12 사용자 지시로 새 EXE를 생성하지 않고 저장소의 기존 EXE ZIP·체크섬을 제거했다. 현재는 [편집 Runner 안내](WINDOWS_RUNNER_EDITABLE.md)를 따른다. 아래 실행·빌드 절차와 해시는 당시 근거이며 현재 배포 파일이 있다는 뜻이 아니다. 소스·호환 코드와 시험 이력은 남겨 기존 설치의 운영/복구 근거를 보존한다.

당시 ZIP `dist/windows-runner/BSP-Windows-Runner.zip`은 소스 `792d862645a7113f86f2932b112c5222b7c4a64f`, 27,889,244 bytes, SHA-256 `4809e0cee8de08bff0d1d0211f9b59385af8905a01348e0f5f4ef06784f65f0c`다. 압축 해제 smoke 10 PASS 및 source snapshot 합성 검증은 [실행 기록](../testing/runs/20261106-setup-commands.md)을 따른다. 회사 인수는 별도다.

RQ-59의 직접 실행·진단·포트 저장은 [실행과 진단 안내](RUN_AND_DIAGNOSE.md)를 따른다. 새 ZIP은 빌드·로컬 검증됐다. 아래 기존 ZIP 설명은 해당 기존 배포본의 이력이다.

Runner의 Python·의존성을 포함한 ZIP이다. 회사 노트북에서 Runner용 `pip install`이나 Node.js 설치 없이 실행한다. Linux 대시보드는 기존대로 Linux에서 실행하며, TC는 회사에서 시험에 사용하던 별도 Windows Python으로 실행한다.

## 회사 PC에서 시작

1. `BSP-Windows-Runner.zip`을 회사 PC의 로컬 폴더(예: `C:\BSP-Runner`)에 압축 해제한다. EXE와 `_internal` 등 동봉 파일을 함께 유지한다. Z:에는 이미지와 TC를 두고 Runner 배포본은 로컬에 둔다.
2. `BSP-Windows-Runner.exe`를 실행한다. 최초에는 **1 연결 설정 / 변경**에서 TC 공유 경로, TC 실행용 `python.exe`, 보드/COM/노드, Linux SSH 주소·계정을 등록한다.
3. 토큰을 생성해 Linux 설정 마법사에 같은 값을 한 번 등록한다. 기존 설정과 토큰이 있으면 재사용한다.
4. Linux에서 기존 `bash scripts/setup.sh`의 **3 저장한 설정으로 실행**을 선택한다.
5. Windows EXE에서 **3 저장한 설정으로 실행**을 선택한다. Runner와 SSH 터널이 함께 시작된다. 내장 의존성을 사용하므로 Windows의 설치 메뉴를 먼저 실행할 필요가 없다.
6. Windows 브라우저에서 `http://127.0.0.1:8766`을 열고 Test 현황의 실제 연결·TC·보드를 확인한다. 연결과 준비 확인 후 대시보드에서 시험을 시작한다.

이후에는 EXE를 열어 3번을 선택한다. 실행 창을 유지한다. 정상 종료는 Ctrl+C로 요청하고 진행 중 작업의 종료를 기다린다. 회사 서버의 SSH 암호나 호스트 키 확인은 OpenSSH가 담당한다.

설정·토큰·실행 이력은 기존 `%USERPROFILE%\.bsp-dashboard\windows`에 남는다. 다른 저장 위치를 사용하던 경우 같은 `--home`을 계속 지정한다.

```powershell
.\BSP-Windows-Runner.exe --home C:\MyBspSettings
```

## 포트가 겹칠 때

아래 옵션을 지원하는 새 배포본에서 실행한다. 기존 ZIP은 자동 갱신되지 않는다. 옵션은 해당 실행에 적용되며 새 배포본에서는 `ports --save`로 명시 저장할 수 있다. 저장 프로파일이 없고 CLI 옵션도 생략하면 `--port` 기본값은 **8771**이다.

Windows의 Runner 포트만 바꾸려면:

```powershell
.\BSP-Windows-Runner.exe --port 18771
```

이 경우 Windows Runner는 `127.0.0.1:18771`에서 기다리고 Linux는 기존 `127.0.0.1:8771`로 접속한다. SSH가 두 포트를 연결하므로 Linux 설정은 그대로 사용한다. 브라우저용 Windows 8766도 사용 중이면 `--dashboard-port 18766`을 추가하고 `http://127.0.0.1:18766`을 연다.

| 옵션 | 위치·의미 | 기본값 |
|---|---|---|
| `--port`, `--runner-port` | Windows Runner의 loopback 포트 | 8771 |
| `--dashboard-port` | Windows 브라우저의 loopback 포트 | 8766 |
| `--remote-runner-port` | Linux SSH 역방향 터널의 loopback 포트 | 8771 |
| `--remote-dashboard-port` | Linux Dashboard API 포트 | 8766 |
| `--ssh-port` | Linux SSH 접속 포트; 이번 실행에서 저장값보다 우선 | 저장값, 없으면 22 |

Linux 쪽 포트까지 바꾸는 예시는 양쪽에서 다음과 같다.

```powershell
.\BSP-Windows-Runner.exe --port 18771 --dashboard-port 18766 --remote-runner-port 28771 --remote-dashboard-port 28766 --ssh-port 2222
```

```bash
bash scripts/setup.sh --remote-runner-port 28771 --remote-dashboard-port 28766
```

Linux에서는 최초에 메뉴 **1 연결 설정 / 변경**에서 새 `http://127.0.0.1:28771` URL을 확인·저장한 뒤 **3 저장한 설정으로 실행**한다. 기존 URL을 몰래 바꾸지는 않는다. 이후에도 같은 인자를 사용한다. Windows 메뉴 3을 실행한 뒤 브라우저는 `http://127.0.0.1:18766`으로 접속한다. SSH 포트는 서버가 실제 사용하는 값이어야 한다.

포트는 1~65535의 정수이며 같은 PC의 Dashboard와 Runner 포트를 같게 지정할 수 없다. 포트 점유·예약 오류가 나오면 기존 프로세스를 임의 종료하지 않고 다른 로컬 포트를 지정한다. `remote port forwarding failed`는 Linux의 해당 역방향 포트 점유나 SSH 포워딩 정책도 확인해야 한다. Windows에서 포트를 바꾸는 것만으로 서버 정책을 변경하지는 않는다. 메뉴 **4 실행기 연결 점검**도 지정한 포트에서 읽기 전용으로 조회한다.

## 별도로 필요한 환경

| 항목 | 준비 |
|---|---|
| Runner용 Python·패키지 | ZIP에 포함; 별도 pip 설치 없음 |
| 회사 TC Python·TC 전용 패키지 | 기존 TC 실행에 성공한 Windows 환경 |
| SSH | Windows OpenSSH 클라이언트와 Linux의 포트 포워딩 허용 |
| TC·이미지 | 노트북에서 읽을 수 있는 공유 폴더 |
| 보드 | COM/USB 드라이버와 실제 연결 |
| 자동 퓨징 | 검토한 배치·fastboot·콘솔 설정과 별도 활성화한 프로파일 |

이 문서의 과거 Runner 배포본은 TC 전용 패키지를 자동 설치하지 않는다. 현재 소스 진입점의 공개 도구 준비와 회사가 제공한 패키지의 검증 설치는 [최신 설치 안내](../agents/PLUGIN_CONTROL_API.md)를 따른다. 일반 TC 실행과 이미지 자동 퓨징 설정은 [Windows Runner](WINDOWS_RUNNER.md), [설정 마법사](SETUP_WIZARD.md), [자동 퓨징 계약](../design/AUTOMATIC_FLASH_TEST.md)을 따른다. 자동 퓨징을 켜기 전 실제 회사 설정과 배치를 검증한다.

## 업데이트와 복원

진행 중 작업을 정상 종료한 후 새 배포본을 별도 로컬 폴더에 압축 해제해 실행한다. 기존 설정 폴더를 삭제하거나 runtime을 새로 만들어 UNKNOWN 상태를 우회하지 않는다. 이 변경은 설정/DB schema 이전을 수행하지 않는다. 문제가 있으면 배포본만 이전 버전으로 바꾸고 같은 설정·runtime을 사용한다. 회사 TC용 Python과 시스템 정책은 자동 변경하지 않는다.

## 현재 소스 실행으로 전환

이 문서의 EXE 배포는 과거 버전 기록이다. 2026-11-14에 EXE 전용 builder·spec·build lock을 제거했으며 새 EXE는 생성하지 않는다. 현재 Windows 실행은 루트 `board-connector.cmd`를 사용한다. 편집형 소스 bundle 조립은 `scripts/build-connector-bundle.cmd`와 [편집형 배포 안내](WINDOWS_RUNNER_EDITABLE.md)를 따른다. 과거 시험·독립 리뷰·회사 인수 미실행 기록은 [기존 실행 기록](../testing/runs/20261104-portable-runner.md)에 보존한다.
