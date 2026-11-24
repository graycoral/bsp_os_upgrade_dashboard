# 대시보드·보드 커넥터 강제 종료

사용자가 명시적으로 실행하는 로컬 비상 명령이다. 정상 종료와 별도로 제공한다. 진행 중인 TC·플래싱·빌드도 중단할 수 있으며, 명령 성공은 시험 성공이나 보드의 안전 상태를 뜻하지 않는다. 예약·DB·실행/UNKNOWN 기록은 지우지 않는다.

## Linux Agent Monitor

저장소 또는 전체 전달 폴더 최상위에서 실행한다.

```bash
bash run.sh force-stop
```

해당 설치 home의 supervisor·API·Worker와 확인한 소유 하위 프로세스를 종료한다. 보드 커넥터나 SSH로 다른 호스트에서 실행 중인 외부 작업까지 종료됐다고 간주하지 않는다. 기존 안전 종료는 `bash run.sh stop`이며 작업이 있으면 보류할 수 있다. 강제 종료는 그 작업 게이트를 사용하지 않는 별도 명시 명령이다.

관리자를 직접 호출하거나 다른 설치 home을 사용한다면 다음처럼 같은 home/runtime을 지정한다.

```bash
python3 apps/agent-monitor/manage.py force-stop --home /path/to/existing-home --runtime /path/to/existing-runtime
```

`run.sh`를 사용할 때 기존 `BSP_RUNTIME` 또는 `--runtime`, `--home` 지정은 계속 유지한다. 종료할 설치본의 설정을 다른 runtime에 연결하지 않는다.

## 보드 커넥터

기본 Profile home은 `%USERPROFILE%\.bsp-dashboard\windows`다. 기본 경로로 실행했다면 경로 입력 없이, 종료할 Windows PC의 전체 소스 폴더에서 아래 명령 하나를 실행한다.

```powershell
.\board-connector.bat --force-stop
```

정상 종료 중 Manager가 Host 상태를 확인하지 못하면 `STOP_READINESS_UNAVAILABLE`를 돌려준다.

구형 설치본이 SSH 소유권 기록 누락으로 종료되지 않을 때는 [단일 복구 스크립트](../../deliveries/connector-recovery/stop-board-connector.py)를 Windows PC에 저장한 뒤 `py -3 .\stop-board-connector.py`로 실행할 수 있다. 표준 라이브러리만 사용하며 기본 Profile home은 같다.

사용자 지정 home이 있다면:

```powershell
.\board-connector.bat --force-stop --home "D:\existing-connector-home"
```

해당 home의 Manager·Host·SSH 및 확인한 소유 하위 프로세스를 종료한다. 브라우저 탭은 남을 수 있으며 다시 접속할 수 없는 화면이 된다. Linux 서버는 별도이므로 Linux의 강제 종료 명령도 그 호스트에서 실행한다. GUI의 연결 종료는 기존 안전 검사를 유지한다. 이 명령은 패키지 설치·공개 도구 준비·GUI 열기·장비 접속을 시작하지 않는다. 지원 Python은 이미 사용 가능해야 하며 없으면 설치 없이 실패한다.

## 결과와 재시작

- `FORCE_STOPPED`: 이번에 식별한 로컬 소유 프로세스의 종료를 확인했다. 결과의 `execution_state=UNKNOWN`을 시험 PASS나 장비 준비 완료로 해석하지 않는다.
- `FORCE_STOP_PENDING`: 부분 종료·권한·기록·프로세스 탐색/종료 확인이 남았다. 종료 대상과 상태를 `force-stop.json`에 보존하며 같은 명령으로 재시도한다. pending 상태에서는 같은 설치본의 새 시작을 차단한다.
- `FORCE_STOP_BLOCKED`: 소유권을 확인할 수 없다. 포트 점유자나 이름이 같은 모든 Python 프로세스를 추측해 종료하지 않는다. OS 소유권 기록이 없는 과거 Monitor 실행본은 먼저 정상 종료·갱신이 필요하다. 구버전에서 SSH의 PID·생성 시각을 기록하지 않았을 때의 자동 복구는 아래를 따른다.

구형 SSH 실행 기록이 남으면 같은 명령이 먼저 이 설치본의 소유권을 확인한 Manager·Host·SSH를 정리한다. 구형 런처가 살아 있으면 해당 프로세스 트리를 확인하고, 이미 종료됐으면 Windows 프로세스 목록에서 해당 런처의 자식 SSH가 남았는지 확인한다. 다른 부모의 SSH와 재사용된 PID의 새 프로세스는 보존한다. 남은 후보가 없으면 `FORCE_STOPPED`다. 소유권을 입증할 수 없는 SSH가 실제로 남았으면 후보 PID를 표시하고 `FORCE_STOP_PENDING`으로 유지한다. 해당 SSH가 종료된 후 같은 명령을 다시 실행하면 상태를 재검사한다.

Windows에서 부모 종료 후의 탐색 자체가 실패하면 `tree_unverified=true`로 남긴다. 재시도는 저장된 대상을 종료하더라도 누락 가능성이 있는 트리를 자동 성공으로 바꾸지 않는다. 이 경우 OS에서 남은 소유 프로세스를 확인하고 기록과 함께 복구해야 한다. marker·DB·예약을 지워 강제 성공 처리하지 않는다.

기록은 Linux `<설치 home>/force-stop.json`, Windows `<커넥터 home>/runtime/force-stop.json`이다. OS PID와 생성 세대만 저장하며 비밀번호·SSH 키는 저장하지 않는다. Linux는 pidfd를 지원하는 환경, Windows는 process handle 권한이 필요하다. 새 코드로 시작한 Monitor는 소유 supervisor/API/Worker 세대를, 커넥터는 SSH 세대를 함께 기록한다.

종료 확인 후 평소 명령 `bash run.sh` / `.\board-connector.cmd`로 다시 시작한다. 기존 시작 시 복구가 중단된 실행을 UNKNOWN으로 다루며 종료·보드 상태를 확인하기 전 자동 PASS·예약 해제를 하지 않는다. 외부 작업의 실제 종료는 별도 근거가 필요하다. [계약](../design/BOARD_CONNECTOR_CONTRACT.md), [검증·미실행 범위](../testing/runs/20261117-connector-cleanup.md), [회사 전달](../porting/PORT-009.md).

BAT는 기존 CMD를 호출하므로 `board-connector.cmd --force-stop`도 같은 명령이다. `--server-port` 설정 변경과 강제 종료를 한 호출로 결합하지 않는다.
