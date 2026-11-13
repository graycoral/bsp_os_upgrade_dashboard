# Linux Dashboard + TEST BOARD CONNECTOR (Windows)

현재 Windows 사용자는 저장소 루트의 `board-connector.cmd`로 설치 확인과 GUI 실행을 함께 처리한다. [현재 가이드](TEST_BOARD_CONNECTOR_GUI.md)를 먼저 따른다. 아래는 기존 windows-http 수동 구성과 고급 단독 Host 실행 설명이다.

보드 커넥터 GUI는 [설치·사용·연동 가이드](TEST_BOARD_CONNECTOR_GUI.md)를 따른다. 아래는 기존 CLI 실행·배포 안내다.

편집 가능한 오프라인 배포는 [편집 Runner 안내](WINDOWS_RUNNER_EDITABLE.md)를 따른다. 소스 수정은 재시작에 반영되고 재포장할 수 있다. 회사 PC에서 Runner용 pip는 필요 없다. 로컬 검증을 완료했고 실제 회사 인수는 별도다.

2026-11-12부터 새 EXE는 생성하지 않고 저장소의 기존 EXE 배포 ZIP·체크섬을 제거했다. 현재 전달·사용은 [편집 Runner 안내](WINDOWS_RUNNER_EDITABLE.md)를 따른다. [포터블 EXE 안내](WINDOWS_RUNNER_PORTABLE.md)는 과거 이력이다. 아래 소스 기반 설치도 유지한다. 회사 TC용 Python은 별도로 사용한다. 웹 재빌드만으로 TEST BOARD CONNECTOR를 재설치하지 않는다.

처음 설정할 때는 [단계별 설정 마법사](SETUP_WIZARD.md)를 사용한다. Linux `bash scripts/setup.sh`, Windows `scripts\setup.cmd`가 입력을 저장하고 다음 실행에 재사용한다. 아래 내용은 수동 구성 및 연결 계약이다.

사용자 확인(2026-11-03): Windows 탐색기로 Linux 공유 TC 경로를 열고 그곳의 Python 스크립트를 Windows에서 실행하면 보드 시험이 가능했다. 파일 저장 위치는 Linux지만 Python 프로세스와 COM 접근은 Windows에 있다.

이번 구현은 이 저장소의 Dashboard에서 일반 TC 실행을 관리하는 경로다. 실제 회사 TC·공유 폴더·SSH·COM 인수는 사용자가 수행한다. 자동 시험은 임시 파일의 가짜 Python TC와 가짜 COM 목록을 사용한다. 요구사항 RQ-46, 시험 T-127~130.

RQ-56/D-60에서는 환경 설정 또는 Test 현황의 공유 TC 소스 편집기로 Linux 서버 폴더나 Gerrit/GitHub HTTPS·SSH clone URL을 검사하고 실제 branch를 선택·적용할 수 있다. 새 소스의 목록과 Windows 실행에는 서버가 준비한 같은 고정 파일을 사용한다. Linux 폴더를 Windows에 별도로 mount할 필요가 없으며 기존 `source_root`는 공유 소스로 돌아갈 때와 자동 퓨징에 계속 사용한다. TEST BOARD CONNECTOR를 함께 업데이트해야 하며 구 실행기는 새 소스 실행을 거부한다. 자세한 API·한도·스냅샷 전송·복구 기준은 [단일 소스/실행 계약](../design/GUI_TEST_CONTRACT.md#tc-소스-등록과-고정-실행--rq-56--d-60)을 따른다.

Git 인증은 Linux API/worker 서비스 계정에 미리 설정한다. SSH agent/기본 키와 known_hosts 또는 사용자 global Git credential helper를 사용하며 브라우저 URL에 토큰·비밀번호를 넣지 않는다. 실제 회사 저장소 인증·clone·장비 인수는 별도다. 새 소스는 기본 metadata를 사용하므로 기존 Windows source_root용 metadata를 가져오지 않는다.

```text
Windows 브라우저 ── SSH -L ──> Linux Dashboard API + GUI worker
                                 │ 실행 요청 / 로그·결과 조회
                                 └── SSH -R ──> TEST BOARD CONNECTOR (127.0.0.1:8771)
                                                 ├─ 공유 폴더 TC → 로컬 snapshot
                                                 └─ Windows Python → COM → 보드
```

브라우저나 Linux가 Windows COM을 직접 열지 않는다. TEST BOARD CONNECTOR에 설정한 Python이 TC를 실행하며, Single은 COM A를 `-p`로, Dual은 보드별 노드명을 `-n`/`-n2`로 전달한다. 기존 Dual COM A/B 명령도 별도 프로파일로 유지할 수 있다. 공유 폴더가 Linux에 있다는 이유로 Linux Python에서 실행하지 않는다.

## 1. TEST BOARD CONNECTOR 준비

이 저장소와 `apps/gui-test/requirements.lock` 의존성을 설치한다. 회사 TC가 필요로 하는 Python 패키지는 **기존에 TC 실행에 성공한 Windows Python 환경**에 설치되어 있어야 한다. 새 실행기는 TC 의존성을 자동 설치하지 않는다.

`apps/gui-test/config/windows-runner.example.json`을 저장소 밖의 개인 설정 파일로 복사하고 다음 값을 수정한다.

- `source_root`: 탐색기에서 접근하는 UNC 공유 경로 또는 드라이브 경로. 예제 `\\linux-server\tc-share`는 실제 주소로 바꾼다. 전체 공유 루트 대신 해당 TC와 필요한 모듈·데이터가 있는 폴더를 지정한다.
- `python`: TC를 실행하던 Windows `python.exe`의 절대 경로.
- `boards`: Windows PC 이름, 사용자가 관리하는 보드 ID, 실제 COM 번호와 Dual용 `node`(예: `n295_sadk`, `n296_sadk`). 같은 호스트의 서로 다른 COM과 노드명을 사용한다. 노드명은 COM 번호나 board_id에서 추정하지 않는다. 예제 COM7/COM8 중 COM8은 예시이므로 실제 포트로 바꾼다. 연결된 COM 열거와 설정 일치만 검사하며 보드 이미지·실제 보드 일련번호를 입증하지 않는다.
- `metadata`: 선택 사항. 상대 TC 경로별 `timeout`, `after`, `id`, `parser` 등을 지정한다. 기본 제한 시간은 10초다. 실제 TC에 맞게 명시한다.

예: `"metadata": {"single/boot.py": {"timeout": 120}, "dual/pair.py": {"timeout": 300}}`.

현재 소스는 실행기·등록·플러그인 연결 토큰을 요구하지 않는다. Linux API/Worker와 Windows 커넥터를 함께 갱신한다. loopback 제한과 SSH 인증은 유지한다.

Windows PowerShell, 저장소 루트:

```powershell
python -m pip install -r apps/gui-test/requirements.lock
python -m backend.gui_test.execution.host --config C:\GuiTestConfig\windows.json --runtime C:\GuiTestRuntime --port 8771
```

실행기는 `127.0.0.1:8771`에만 바인딩한다. 실행 터미널을 유지한다. TC 경로와 runtime은 서로 포함하지 않는 별도 디렉터리여야 한다.

## 2. Linux Dashboard 설정·빌드

Linux의 저장소에서 Python 가상환경과 의존성을 설치한 후:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock
bash scripts/build.sh dashboard
mkdir -p .runtime
cp apps/gui-test/config/dashboard-windows.example.json .runtime/gui-test.json
bash scripts/start.sh
```

`.runtime/gui-test.json`이 있으면 `windows-http` 연결을 사용한다. 잘못된 설정을 Mock로 자동 대체하지 않는다. 파일이 없으면 기존 Mock 모드를 유지한다. 기존 데모 DB는 보존하며 실제 실행 기록은 `.runtime/gui-test-dashboard-windows/runs.db`에 저장한다. 서버의 실제 TC 파일 경로는 별도로 지정하지 않는다. TEST BOARD CONNECTOR가 공유 폴더를 읽어 TC 목록과 소스 기준을 제공한다.

## 3. Windows에서 SSH 터널 연결

Windows의 별도 터미널에서, 실제 Linux 계정·주소로 교체:

```powershell
ssh -NT -o ExitOnForwardFailure=yes -o ServerAliveInterval=15 -o ServerAliveCountMax=3 -L 8766:127.0.0.1:8766 -R 127.0.0.1:8771:127.0.0.1:8771 developer@linux-server
```

Linux SSH 서버가 포트 포워딩을 허용해야 한다. `-L`은 Windows 브라우저 접속용, `-R`은 Linux에서 TEST BOARD CONNECTOR를 부르기 위한 역방향 터널이다. Windows OpenSSH 서버나 외부 공개 실행기 포트는 필요하지 않다. SSH 인증은 필요하다. 사용 중인 포트가 겹치면 각 터널 끝점과 해당 서비스 포트를 맞춘다. TEST BOARD CONNECTOR와 Linux 역방향 포트의 숫자가 같을 필요는 없다.

마법사/EXE는 `--port 18771`로 TEST BOARD CONNECTOR 포트만 바꿀 수 있다(생략 시8771). 이때 SSH는 `-R 127.0.0.1:8771:127.0.0.1:18771`로 연결하고 Linux JSON의 URL은 기존8771을 유지한다. `--dashboard-port`는 Windows 브라우저 쪽 포트, `--remote-runner-port`와 `--remote-dashboard-port`는 Linux 쪽 포트다. [옵션과 양쪽 실행 예시](WINDOWS_RUNNER_PORTABLE.md#포트가-겹칠-때)를 참조한다. 고급 수동 Host 실행은 `--port` 옵션을 사용하고 별도 SSH 명령의 `-R` 대상 포트를 같은 값으로 지정한다.

## 4. Dashboard에서 실행

1. Windows 브라우저에서 `http://127.0.0.1:8766` → **Test 현황**. 설정이 적용되면 `WINDOWS RUNNER`를 표시한다. 연결이 실패하면 오류를 표시하며 데모로 되돌리지 않는다.
2. 소스는 `shared`. TC 목록/전체 선택과 보드·COM을 확인한다.
3. **TC 실행 명령 설정**에서 프로파일을 저장한다. Single 기본값은 각 줄에 `python3`, `{tc_path}`, `-p`, `{com_a}`다. `python`/`python3`는 Windows 설정의 실행 파일로 치환되며, `{tc_path}`는 검증된 로컬 snapshot의 절대 TC 경로다. 사용자 확인 명령 `python3 tc1.py -p COM7`에 맞춰 TC 경로와 선택 COM을 전달한다. 기존 저장 프로파일은 덮어쓰지 않으므로 필요하면 Single 필드를 수정하고 저장한다.
4. Single COM A는 `{com_a}`, Dual 노드명은 `{node_a}`/`{node_b}`를 각각 별도 줄에 넣는다. Single은 `-p` 뒤에 COM 이름 전체(예: `COM7`)를 전달한다. Dual 기본값은 각 줄에 `python3`, `{tc_path}`, `-n`, `{node_a}`, `-n2`, `{node_b}`이며 사용자 예 `python3 tc_2.py -n n295_sadk -n2 n296_sadk`에 대응한다. Board A/B의 등록 node 값이 없거나 설정과 다르면 시작을 거부한다. 기존 Dual COM 쌍과 노드명 쌍을 섞지 않는다. 셸, `python -c`, 임의 실행 파일은 지원하지 않는다.
5. Preflight → 테스트 시작. stdout/stderr의 정확한 `Test Result: PASS` 또는 `Test Result: FAIL`과 종료 코드로 기존 엄격 판정기를 적용한다. 기존 TC 출력이 다르면 지원 parser 설정으로 맞추고 시험한다. 결과가 없거나 프로세스 종료가 불명확하면 PASS가 아니다.

일반 TC 실행·Run/Attempt·반복·FAIL Retry·리포트를 Dashboard에서 사용한다. **실제 BSP Job의 device_test 자동 완료는 미구현**이다. 이미지 동일성 증거·TC↔필수 사례 매핑·현행 Attempt 연결이 없으므로 이 모드에서는 Job 선택과 데모 Job 생성 UI를 제공하지 않는다. 기존 수동 장비 시험은 유지한다.

## 중단·복구·소스 경계

- 공유 소스 파일·metadata 해시를 고정하고 매 Attempt 전에 재검사한다. Python 파일뿐 아니라 비숨김 보조 데이터도 로컬 snapshot에 복사한 뒤 실행한다. 소스가 바뀌면 이전 기준으로 새 TC를 실행하지 않는다.
- `.git`, `.venv`, `venv`, `__pycache__`, `node_modules`, `.runtime`, 숨김 경로는 복사하지 않는다. 링크 경로는 거부한다. 최대 10,000파일/128MiB, 개별16MiB이며 한도를 넘으면 명시적으로 거부한다. snapshot 밖의 절대 경로에 의존하는 TC는 별도 환경 조정이 필요하다.
- Windows Job Object에 TC와 자식 프로세스를 묶는다. 종료를 확인한 경우에만 완료 처리한다. 내부 구현 근거: [Microsoft Job Objects](https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects).
- 실행 요청 ID를 디스크에 기록하여 응답 유실 후 중복 실행을 방지한다. 연결이 끊겨 10초 동안 lease 갱신이 없으면 TEST BOARD CONNECTOR가 프로세스 트리를 중단한다. Linux는 연결 유실만으로 종료를 추정하지 않고 UNKNOWN 및 예약을 유지한다. 재연결 후 **Windows 종료 / 연결 재확인**으로 종료 증거를 조회하고 명시적으로 재개한다.
- 실행기 자체가 비정상 종료하면 기존 RUNNING을 UNKNOWN으로 보존하고 새 TC 실행을 차단한다. 현재 자동 프로세스 재접속은 미구현이다. runtime을 삭제하여 시험 이력을 없애거나 실행 불명 상태를 우회하지 않는다.
- 실행기는 한 번에 한 TC만 실행한다. 다른 프로그램이 COM을 사용 중이면 실제 Python TC가 오류를 보고할 수 있다. RBC/RBM 보드 식별 및 다른 독립 프로그램과 공통 물리 예약은 별도 인수 범위다.
- 마스킹된 로그·snapshot·Windows 실행 DB가 runtime에 남는다. 서비스가 사용 중인 runtime은 옮기거나 지우지 않는다. 출력은 64KiB 제한이며 초과 시 ERROR다. 실제 모델 호출·BSP 수정/빌드/플래시·Jira 작업을 이 안내의 시험으로 수행하지 않는다.

현재 검증 범위와 미실행 항목은 [이번 실행 기록](../testing/runs/20261103-windows-runner.md)을 따른다.

노드명 설정을 추가/변경하면 TEST BOARD CONNECTOR를 안전하게 종료한 뒤 설정을 갱신하고 다시 시작한다. 대시보드의 보드 목록을 새로 불러와 확인하고, 과거 연결 프로파일도 새 매핑으로 저장해야 한다. 기존 Run/실행 중 snapshot은 자동으로 바꾸지 않으며 현재 설정과 다른 과거 매핑의 재개는 차단된다.

## 느린 TC 카탈로그 조회 · RQ-58 / D-62

Linux API/worker와 웹을 갱신하면 기존 TEST BOARD CONNECTOR `/v1/catalog` 서버에 대한 읽기 제한시간이 기본100초가 된다. 웹 소스 설정에서1~600초 정수를 저장할 수 있으며 연결 실패 중에도 수정 가능하다. 다음 목록 요청부터 반영하고 인증·보드·실행 제어·lease·실제 TC 실행 제한시간은 유지한다. 저장 파일·API·오류 계약은 [GUI Test 계약](../design/GUI_TEST_CONTRACT.md)의 RQ-58 절을 따른다.

승인된 기존 Runner ZIP/EXE는 재빌드·교체하지 않는다. 기존 EXE의 메뉴4는 이전5초 조회를 유지한다. 새 단계별 진행 표시·메뉴8·`--catalog-timeout`은 갱신된 소스 마법사에만 제공되며 [마법사 안내](SETUP_WIZARD.md)를 따른다. 카탈로그 호출자 변경은 새 소스 snapshot capability 지원 근거가 아니다. 실제 회사 공유 폴더에서의 대기 성공과 SSH·장비 인수는 별도 NOT_RUN이다.

## 선택 기능: BSP 자동 이미지 퓨징·TC

일반 TC 실행과 별도로 [자동 퓨징 계약](../design/AUTOMATIC_FLASH_TEST.md)의 Linux device-test.json/Windows flashing 프로파일을 활성화하면 BSP 테스트 단계에서 콘솔 → 배치 퓨징 → 부팅 → TC를 이어간다. 일반 GUI Run의 운영 Job 자동 완료는 여전히 차단된다. 퓨징은 TC 취소/10초 lease 정책을 사용하지 않는다. 실제 배치와 보드 인수는 별도로 수행한다.
