# Windows Runner 실행파일 사용

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

## 별도로 필요한 환경

| 항목 | 준비 |
|---|---|
| Runner용 Python·패키지 | ZIP에 포함; 별도 pip 설치 없음 |
| 회사 TC Python·TC 전용 패키지 | 기존 TC 실행에 성공한 Windows 환경 |
| SSH | Windows OpenSSH 클라이언트와 Linux의 포트 포워딩 허용 |
| TC·이미지 | 노트북에서 읽을 수 있는 공유 폴더 |
| 보드 | COM/USB 드라이버와 실제 연결 |
| 자동 퓨징 | 검토한 배치·fastboot·콘솔 설정과 별도 활성화한 프로파일 |

Runner 설치 문제를 해결하는 배포본이며 TC 전용 패키지를 자동 설치하지 않는다. 일반 TC 실행과 이미지 자동 퓨징 설정은 [Windows Runner](WINDOWS_RUNNER.md), [설정 마법사](SETUP_WIZARD.md), [자동 퓨징 계약](../design/AUTOMATIC_FLASH_TEST.md)을 따른다. 자동 퓨징을 켜기 전 실제 회사 설정과 배치를 검증한다.

## 업데이트와 복원

진행 중 작업을 정상 종료한 후 새 배포본을 별도 로컬 폴더에 압축 해제해 실행한다. 기존 설정 폴더를 삭제하거나 runtime을 새로 만들어 UNKNOWN 상태를 우회하지 않는다. 이 변경은 설정/DB schema 이전을 수행하지 않는다. 문제가 있으면 배포본만 이전 버전으로 바꾸고 같은 설정·runtime을 사용한다. 회사 TC용 Python과 시스템 정책은 자동 변경하지 않는다.

## 소스에서 빌드

Windows CPython 3.12.10 x64에서 전용 가상환경을 만들고 `apps/gui-test/requirements.lock`과 `packaging/windows-runner-build.lock`을 설치한다. 준비된 환경에서 다음을 실행한다.

```powershell
.\apps\gui-test\.build\runner-venv\Scripts\python.exe scripts\build_windows_runner.py
```

결과는 `dist/windows-runner/`의 폴더·ZIP·SHA256이다. 빌드는 의존성을 자동 설치하지 않는다. 실제 로컬 시험·독립 리뷰·미실행 인수 범위는 [이번 실행 기록](../testing/runs/20261104-portable-runner.md)에서 확인한다. 회사 PC·SSH·실장비 T-160는 별도 인수다.
