# 보드 커넥터 실행과 연결 진단

## 현재 브라우저형 보드 커넥터

플러그인과 같은 고정 버전의 전체 소스를 Windows에 받는다. [다운로드·설치 안내](TEST_BOARD_CONNECTOR_GUI.md#어디서-받아-실행하는가)를 따른다. 저장소 루트에서 실행한다.

```powershell
.\board-connector.cmd
```

최초에는 실행 환경과 공개 필수 도구를 준비하고 브라우저 화면을 연다. 이후에도 같은 CMD를 사용한다. Linux 서비스는 먼저 `bash run.sh --port 8765` 등 실제 저장된 회사 포트로 준비한다. Windows에서 플러그인 연결 파일을 가져오고 COM·보드와 연결 상태를 확인한다.

CMD 진입·Python·파일·패키지를 설치 없이 확인하려면:

```powershell
.\board-connector.cmd --diagnose
```

이 진단은 파일·Python import 검사다. Manager·SSH·COM·TC를 시작하지 않으며 보드 통신 성공 판정도 아니다. 연결 후 상태등·연결 로그·공통 오류·보드 콘솔은 GUI에서 확인한다. [BC 코드별 조치](TEST_BOARD_CONNECTOR_GUI.md#cmd-경로-오류--번호별-진단과-조치)를 따른다. 기존 사용자 지정 `--home`이 있다면 동일 경로를 계속 전달한다. 브라우저를 닫아도 Manager와 시험 수명은 유지된다.

## 고급 CLI 구성의 설정·진단

이하 `scripts/setup.*`는 기존 CLI Host·SSH 구성과 Linux 설정용이다. 현재 GUI Manager를 실행 중인 home·포트에서 별도 CLI `run`을 기동하지 않는다. CLI 번들의 명령은 [별도 번들 안내](BOARD_CONNECTOR_BUNDLE.md)를 따른다. 과거 EXE 명령은 [과거 배포 기록](WINDOWS_RUNNER_PORTABLE.md)에만 남긴다.

CLI 소스 설정은 `scripts\setup.cmd` 또는 `bash scripts/setup.sh`를 인자 없이 열어 메뉴 1에서 저장한다. 아래는 특정 포트 구성 예시다. 일반 기본값은 커넥터 8771, 브라우저 터널/API 8766이며 저장값과 명시 CLI 값이 우선한다.

```bash
bash scripts/setup.sh ports --remote-dashboard-port 8765 --remote-runner-port 8771 --save
```

```powershell
.\scripts\setup.cmd ports --port 18771 --dashboard-port 18766 --remote-dashboard-port 8765 --remote-runner-port 8771 --save
```

`ports`만 실행하면 유효한 값과 출처를 표시한다. `--save`만 저장한다. Linux는 `<저장소>/.runtime/setup-ports.json`, Windows는 `<선택한 home>/setup-ports.json`을 사용한다. 현재 GUI의 포트는 GUI 환경설정에서 변경하며, 이 CLI 포트 파일이 GUI Manager 설정을 변경하는 것으로 간주하지 않는다.

저장한 CLI 구성에서 Linux는 `bash scripts/setup.sh run`, Windows는 `.\scripts\setup.cmd run`을 실행한다. 해당 CLI 구성의 Host·SSH 터널을 유지한 상태에서 별도 터미널로 진단한다.

```powershell
.\scripts\setup.cmd doctor --only identity
.\scripts\setup.cmd doctor --only boards
.\scripts\setup.cmd doctor --only catalog
.\scripts\setup.cmd doctor --only catalog --catalog-timeout 180
```

Linux에서도 `bash scripts/setup.sh doctor` 뒤에 같은 선택 인자를 쓴다. CLI 번들에서는 `.\setup.cmd doctor ...` 또는 `.\diagnose.cmd ...`를 사용한다. 진단은 TC·퓨징을 실행하지 않는다. catalog 조회는 고정 소스의 임시 snapshot을 만들 수 있다. 목록 대기시간과 TC 실행 제한시간은 별개다.

Windows 로컬 진단이 성공하고 Linux가 실패하면 역방향 SSH 터널과 실제 포트를 확인한다. 포트 변경은 기존 CLI 실행을 Ctrl+C로 정상 종료한 뒤 적용한다. `UNKNOWN`·예약·종료 근거를 지우거나 중복 Host를 실행해 우회하지 않는다. 실제 회사 Windows·SSH·공유 폴더·장비 인수는 별도다.
