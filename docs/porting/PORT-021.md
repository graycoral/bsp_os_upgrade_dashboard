# PORT-021 · 다중 플러그인 작업 소유와 Agent Monitor

고정 소스는 `c02d60e8bc6738d924e4740d0352cb4303df7e40`이다. [회사 복사 폴더·검증값·직전 버전](../../deliveries/company-handoff-c02d60e/00_START_HERE.md)을 확인한다.

RQ-87 · T-324. 선행 전달본은 `d47286a`(PORT-020)이다. [설계와 권한 범위](../design/MULTI_PLUGIN_OWNERSHIP.md), [원본 시험 기록](../testing/runs/20261129-multi-plugin-ownership.md)을 참조한다.

## 회사에서 적용할 위치

회사 플러그인 설치 담당자는 전달 폴더의 패키지 전체를 새 버전 디렉터리로 복사한다. Windows 장비 PC는 같은 소스로 생성한 커넥터 폴더를 사용한다. 회사 플러그인 소유자는 작업 생성·재개·종료 및 모니터 열기 훅을 연결하고, 각 창의 영속 작업 ID를 같은 작업의 명령에 전달한다. 계정 자격은 회사 보안 채널로 개별 계정에 전달하고 Git과 공용 설치 폴더에서 제외한다. Windows 운영자는 공유 모드, 계정 및 Monitor 목적지를 관리한다. Linux 쪽 파일 접근은 해당 OS 계정 권한을 따른다.

Windows 장비에서 실행하는 TC와 설치 스크립트는 기존 Runner OS 계정의 권한으로 동작한다. 기본 공유 계정은 Windows 운영자가 승인한 실행 입력만 사용할 수 있다. 자체 실행 코드를 게시할 권한까지 회사에서 부여한 작성자에 한해 계정 발급 시 `--trusted-tc-author`를 선택한다. 이 선택은 Windows Runner 권한으로 코드를 실행할 수 있게 하므로 일반 조회·시험 사용자에게 적용하지 않는다.

## 이전과 현지 인수

장비가 유휴일 때 Windows 프로필과 실행 DB, Linux의 설치 프로필과 runtime을 백업한다. 기존 실행 이력의 소유자를 자동 지정하지 않는다. 롤백이 필요하면 유휴 상태에서 운영 서비스 중지 후 직전 패키지와 전환 전 프로필·DB를 함께 복원한다. 전환 이후 기록은 별도 보관한다. 개인 모드로 복원하기 전 공유 서버의 터널과 계정 접근을 닫고 원래 단독 사용 환경에서 다시 연다.

회사 테스트는 같은 계정에서 같은 프로젝트를 두 창으로 열고, 다른 계정에서도 작업을 연 뒤 한 창에서 모의 시험을 시작한다. 실행 소유 창과 다른 두 창의 조작 권한, Windows의 기본 목적지, 각 Linux 창의 모니터 목적지, 창 재개·SSH 재연결·명시적 인계를 확인한다. 실행 중인 화면을 열어 둔 상태에서도 다른 작업으로 전환되지 않는지 확인한다. 회사 적용 커밋, 실제 복사 위치와 통과한 항목을 회사 APPLIED.md에 남긴다.

## Windows 운영자 준비

아래 PowerShell 예시에서 `$Runtime`은 **현재 Host의 executions.db가 있는 디렉터리**, `$Python`은 커넥터의 Python, `$Tool`은 전달된 `agent-monitor/scripts/manage_connector_sharing.py`이다. 먼저 Host를 한 번 초기화하고 온전한 유휴 상태에서 중지한다. 아래의 계정명·포트·설치 이름은 회사 값으로 교체한다.

```powershell
& $Python $Tool --runtime $Runtime enable
& $Python $Tool --runtime $Runtime issue-account alice --output $NewCredentialFile
& $Python $Tool --runtime $Runtime approve-monitor --account alice --monitor-id alice-monitor --ssh-profile default --monitor-port 8766 --protected-monitor-listener --output $NewMonitorKeyFile
& $Python $Tool --runtime $Runtime status
```

Monitor용 Linux 리스너는 설치 전용 네트워크 환경 또는 시스템의 바인딩 정책으로 다른 사용자가 서비스 정지 중에도 주소를 가져갈 수 없게 구성한다. Windows의 열기 브라우저도 허가된 운영자 환경에서 사용한다. 운영자가 확인한 `--protected-monitor-listener`는 이 배포 조건을 기록한다. Host용 Unix 소켓만 보호한 설치에서는 Monitor 리스너 보호를 별도로 준비한다. 계정 자격 파일은 해당 계정으로, Monitor 설치 키 파일은 승인된 Monitor의 운영 계정으로 각각 전달한다. 등록된 Monitor ID에 다른 작업 계정의 접근을 추가할 때는 같은 설치를 지정한다. 이후 커넥터를 기동한다. 다른 계정에는 별도 자격 파일을 발급하고 사용할 Monitor만 승인한다. 동일 서버의 독립 Monitor 프로세스에는 각각 빈 Linux 포트를 지정한다. `default`는 Windows에 저장된 현재 SSH 연결 설정이다. 다른 SSH 계정·키가 필요하면 운영자가 Windows runtime의 `shared-monitor-ssh.json`에 다음과 같이 이름을 지정한 뒤 해당 이름을 `--ssh-profile`에 사용한다.

```json
{"profiles":{"bob-session":{"server":"linux.example","account":"bob","ssh_port":22,"ssh_key":"C:\\Keys\\board-monitor"}}}
```

Windows에서 확인한 현재 Run ID와 소유권 버전으로 인계한다. `$HostPort`는 실제 Windows 로컬 Host 포트다. 인계 성공 후 새 작업은 현재 소유권 버전으로 조작한다.

```powershell
& $Python $Tool --runtime $Runtime status --run-id $RunId
& $Python $Tool --runtime $Runtime --host-port $HostPort handoff --run-id $RunId --task-id $NewTaskId --expected-epoch $CurrentEpoch
& $Python $Tool --runtime $Runtime --host-port $HostPort revoke-account alice
```

인계와 계정 폐기는 독립적인 운영 사례다. 계정 폐기는 해당 계정의 모든 작업 접근을 종료하므로 더 이상 계정 접근을 허용하지 않을 때만 실행한다.

## Linux 공유 전송 경로

공용 서버의 각 플러그인과 Monitor가 Windows Host에 자격을 보낼 때는 관리자가 소유하는 Unix 소켓을 사용할 수 있다. Linux 관리자는 같은 서버에서 사용할 전용 SSH 계정 소유의 소켓 디렉터리를 준비하고, 허용한 계정 그룹에 경로 통과 및 소켓 연결만 허용한다. 디렉터리와 상위 경로는 다른 계정이 쓰거나 교체할 수 없어야 한다. `RUNNER_SOCKET`은 그 절대 경로이며 `TUNNEL_UID`는 소켓 소유 계정의 숫자 UID다. Windows에서 해당 SSH 계정으로 별도 OpenSSH 포워딩을 유지한다. 아래 예시는 이미 검증한 SSH 호스트 키, SSH 키와 Windows Host 포트를 사용한다.

```powershell
ssh -N -o BatchMode=yes -o StrictHostKeyChecking=yes -o ExitOnForwardFailure=yes -R "${RemoteSocket}:127.0.0.1:${HostPort}" $SshDestination
```

Linux SSH 서버가 원격 StreamLocal 포워딩과 승인 그룹의 소켓 접근을 허용해야 한다. 관리자 정책으로 지정한 loopback 포트를 신뢰된 서비스만 점유하도록 보장하는 설치는 자격 가져오기에서 `--trust-protected-loopback`을 선택할 수 있다. 포트가 비어 있거나 `127.0.0.1`로 수신한다는 사실만으로 이 옵션을 사용하지 않는다. 같은 OS 로그인 사용자가 서로의 파일을 읽을 수 있는 환경에서 사람을 격리하려면 각각 별도 Linux 계정을 사용한다.

## Linux 회사 플러그인 연결

`$PLUGIN`은 새 복사 폴더 루트의 `plugin.py`이다. 모니터와 커넥터의 설치·의존성은 PORT-020 절차로 준비한다. 전송한 계정 자격 파일은 해당 Linux 사용자만 읽도록 보관한다. 아래 예시는 활성 창의 작업 ID를 회사 세션에 저장하는 방식이다.

```sh
python3 "$PLUGIN" --connector-port 8771 sharing import --credential-file "$CREDENTIAL_FILE" --sharing-host-socket "$RUNNER_SOCKET" --sharing-host-socket-owner-uid "$TUNNEL_UID"
python3 "$PLUGIN" --monitor-port 8766 --connector-port 8771 monitor ensure --sharing-monitor-id alice-monitor --sharing-monitor-key-file "$MONITOR_KEY_FILE" --no-provision
python3 "$PLUGIN" --project platform-A --connector-port 8771 task create --monitor-id alice-monitor
```

`task create`의 응답에 있는 `task_id`를 회사 작업 레코드에 저장한다. 같은 프로젝트라도 새 작업에는 새 ID를 생성한다. 기존 작업을 다시 열 때는 저장한 ID를 사용한다. 아래 명령의 `TASK_ID`는 해당 창이 보유한 값이다.

```sh
python3 "$PLUGIN" --task "$TASK_ID" --connector-port 8771 task open
python3 "$PLUGIN" --task "$TASK_ID" --connector-port 8771 test runs
python3 "$PLUGIN" --task "$TASK_ID" --monitor-port 8766 --connector-port 8771 monitor open
```

각 창이 별도 자식 프로세스를 관리하면 `BSP_PLUGIN_TASK_ID`를 그 자식 환경에만 전달해도 된다. 커넥터 연결 감시는 Linux 사용자·포트당 하나를 유지한다. Windows에서 작업을 열 때는 운영자가 승인한 Monitor 경로를 확인하고 현재 Run의 작업을 선택한다. Linux에서 열 때는 해당 창의 작업을 선택한다. 열린 탭은 해당 작업의 실행, 단계, 결과와 로그를 조회한다. 공유 Monitor 서비스는 작업 전용 조회 화면을 제공하며 전체 BSP 작업 목록과 Worker 운영은 기존 관리용 Monitor에서 수행한다. 권한이 만료되면 해당 창에서 다시 연다.

## 기본 계정의 시험 실행

Linux 작업 창에서 `test prepare --file "$PREPARED" --build "$BUILD_ID" --tc-root "$TC_ROOT"`으로 입력을 고정한다. 회사 전달 채널로 준비 파일을 Windows 운영자에게 전달한다. Windows 운영자는 작업, TC 소스·설치물 스냅샷과 실행 명령을 대조한 뒤 기존 Host에 도착한 자료를 승인한다. 확정한 파일은 Linux에서 `test send --file "$PREPARED"`로 접수한다. 퓨징이 포함되면 기존 PORT-018의 명시적 확인 옵션을 적용한다. 소스, 설치물 또는 실행 명령을 변경한 경우 변경된 입력을 다시 준비한다. 같은 승인 입력의 재접수는 기존 Run을 돌려준다.

```powershell
& $Python $Tool --runtime $Runtime approve-prepared-run --prepared $PreparedRequestFile
```

개인 모드에서 만들어진 기존 Run은 공유 작업에 인계해도 실행물 승인이 생기지 않는다. 운영자가 보관된 실행 입력과 현재 소유 작업을 확인한 후 아래 명령으로 승인해야 일반 계정이 해당 Run을 다시 실행할 수 있다.

```powershell
& $Python $Tool --runtime $Runtime approve-run-input --run-id $RunId --task-id $CurrentOwnerTaskId
```

## 원본 및 전달본 검증

`bash scripts/test_multi_plugin_ownership.sh feature`는 임시 DB와 loopback 서비스로 작업 권한을 시험한다. `regression`은 기존 직결·복구·패키지 계약, `browser`는 임시 Windows Manager 화면, `package /absolute/path/to/copied-package`는 실제 복사본 검증을 수행한다. Python은 BSP_TEST_PYTHON, 브라우저 실행 파일은 BSP_BROWSER_EXECUTABLE로 지정할 수 있다. 브라우저 검증은 기존 Node/Playwright 설치를 사용한다.

기존 회사 GUI Test 서비스가 공유 Host에서 batch 예약을 수행하는 설치는 Windows에서 `issue-service`로 서비스 자격을 따로 발급한다. GUI Test의 고정 `windows-http` Runner 설정에 `service_credential_file`을 서비스 계정 전용 파일 경로로 지정한다. Unix 소켓을 사용하는 서비스는 `service_ssh_socket`과 숫자 `service_ssh_socket_owner_uid`를 지정한다. 보호된 TCP 설치는 `service_trust_protected_loopback`을 명시적으로 true로 설정한다. 기존 플러그인 페어링 토큰이나 사람이 쓰는 작업 자격을 재사용하지 않는다. 모의 예약 수명주기 및 동시 직결 Run 거절을 회사 인수에서 확인한다.

## 변경 위치

| 전달 패키지 안의 경로 | 담당 동작 |
|---|---|
| `plugin.py`, `agent-monitor/apps/agent-monitor/plugin.py` 및 `manage.py` | 회사 명령 진입, 공유 Monitor 준비와 현재 창의 작업 열기 |
| `agent-monitor/backend/gui_test/standalone/plugin_sharing.py`, `direct_connector_client.py`, `plugin_commands.py` | 계정 파일, 작업별 상태·설정, 정상 요청·응답 유실 후 재접수 |
| `agent-monitor/backend/gui_test/execution/sharing.py`, `sharing_http.py`, `connector_runs.py`, `host.py` | executions.db 추가 테이블, 서버 권한, Run과 입력 고정, 인계·재실행·분석 처리 |
| `agent-monitor/scripts/manage_connector_sharing.py` | 계정·서비스·Monitor 승인, 입력 승인·인계 CLI |
| `agent-monitor/backend/gui_test/connector/monitor_tasks.py`, `ssh_tunnel.py`, `supervisor.py`, `gui.py` 및 `packages/gui-test-ui/src/connector_web/` | Windows 운영자의 작업 선택, 목적지 확인, 웹·Qt 화면 |
| `agent-monitor/backend/api/shared_monitor.py` 및 `shared_monitor_assets/` | Linux 작업용 조회 서버와 작업·Run·TC·로그 화면 |
| `agent-monitor/backend/gui_test/adapters/windows_remote.py`, `core/shared_transport.py`, `core/monitor_identity.py` | 회사 GUI Test 서비스 자격과 보호된 전송 경로 및 Monitor 설치 확인 |

패키지 밖에서 회사가 연결하는 부분은 창 생성·재개 시의 작업 ID 저장, 계정별 자격 배치, 준비 파일의 승인 전달이다. 개인 설치의 기존 connector schema 버전은 4이며 공유 테이블은 별도 버전을 쓴다. 폴더에는 계정 키, 운영 DB, SSH 개인키를 포함하지 않는다.
