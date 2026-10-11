# BSP OS Upgrade Dashboard

BSP OS 업그레이드의 모듈 분석·구현·빌드·검증·수동 장비 시험과 사람의 판단을 관리하는 웹 대시보드입니다.

현재는 **로컬에서 검증한 1차 구현**입니다. 기본 설정으로 외부 서비스 없이 데모를 실행할 수 있습니다. 실제 Linux 서버·OpenCode/Claude/Codex·BSP 빌드·사내 Jira 연결은 환경별 JSON 브리지와 실제 연동 검증이 필요합니다. 데모의 산출물은 시연용 JSON이며 보드에 적용할 OS 이미지가 아닙니다.

## 1. 설치와 실행

실행 서버는 Linux를 대상으로 합니다. 로컬 개발과 자동 시험은 macOS에서 검증했습니다. Python 3.11 이상, Node.js 22.12 이상과 npm이 필요합니다. Windows는 브라우저와 SSH 터널로 접속하며, 현재 worker는 Windows 네이티브 실행을 지원하지 않습니다.

```sh
git clone https://github.com/graycoral/bsp_os_upgrade_dashboard.git
cd bsp_os_upgrade_dashboard
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.lock
npm ci --prefix apps/web
npm run build --prefix apps/web
bash scripts/start.sh
```

1. 브라우저에서 `http://127.0.0.1:8765`를 엽니다.
2. 별도 터미널에서 프로젝트 폴더의 접속 키를 확인합니다.

   ```sh
   cat .runtime/access-token
   ```

3. 로그인 화면의 **접속 키**에 입력하고 **작업 공간 열기**를 누릅니다. 키 값은 설정 JSON이나 GitHub에 올리지 않습니다.

`start.sh`는 API와 worker를 함께 실행합니다. 브라우저를 닫아도 작업은 계속되지만 실행 터미널을 종료하면 프로세스도 종료됩니다. 중지는 `Ctrl+C`, 포트 변경은 `BSP_PORT=8877 bash scripts/start.sh`로 합니다.

Linux에서 장시간 유지하려면 다음 두 프로세스를 같은 계정·프로젝트 폴더·runtime 경로로 서비스 관리자에 각각 등록하세요. 서비스 설치 파일은 아직 제공하지 않습니다. 동일 runtime의 worker는 하나만 실행합니다.

```sh
.venv/bin/python scripts/serve.py --runtime .runtime --port 8765
# 별도 터미널 또는 서비스
.venv/bin/python -m backend.worker.main --runtime .runtime
```

## 2. Windows에서 Linux 화면 접속

먼저 Linux 서버에서 위 API와 worker를 실행합니다. Windows에서 저장소의 PowerShell 스크립트를 실행합니다. 예시 호스트와 계정은 실제 값으로 바꾸세요.

```powershell
.\scripts\connect-windows.ps1 -Server "linux.example.internal" -Account "developer"
```

또는 Windows의 SSH로 직접 연결합니다.

```powershell
ssh -N -L 8765:127.0.0.1:8765 developer@linux.example.internal
```

Windows 브라우저에서 `http://127.0.0.1:8765`를 열고 **Linux 서버의** `.runtime/access-token`으로 접속합니다. 포트가 겹치면 스크립트에 `-LocalPort 8877`을 주고 해당 주소를 여세요. SSH 터널을 닫아도 서버의 API·worker가 살아 있으면 작업 기록과 실행은 유지됩니다.

현재는 두 접속 방식 모두 장비 시험을 사람이 수행합니다. Windows에서 이미지를 내려받아 로컬 장비를 시험하거나 Linux 환경에서 수동 시험한 후 같은 화면에 결과를 등록합니다. 자동 플래시와 보드팜 연결은 후속 범위입니다.

## 3. 환경 설정

왼쪽 **환경 설정**에서 값을 입력하고 **설정 저장**을 누르세요. JSON 파일 가져오기·내보내기도 지원합니다. 저장한 설정은 **새 작업부터 적용**되며 기존 작업의 실행 모드와 소스 기준을 바꾸지 않습니다.

| 설정 | 사용 방법 |
|---|---|
| 실행 방식 | 처음에는 `demo`. 실제 환경용 브리지를 준비한 뒤 `bridge` 선택 |
| Linux 호스트·계정 | 연결 대상 표시 정보. 입력만으로 원격 SSH 실행이 시작되지는 않음 |
| 작업 폴더 | worker가 실행되는 서버의 실제 작업 디렉터리 |
| 소스 기준 | 기존 원본 OS, 벤더 수정본, 새 원본 OS 경로와 고정된 커밋/해시 |
| 에이전트·빌드 명령 | JSON 브리지 실행 파일과 인자 배열. 일반 CLI나 셸 명령을 그대로 넣는 항목이 아님 |
| 모듈 목록 | 모듈 이름과 `boot`(선행)/`main`(나머지) 그룹. 새 작업 생성 때 고정 |
| Jira | 직접 연결 또는 Claude MCP 방식, 주소·프로젝트·인증 환경변수 이름 |
| 상세 JSON 설정 | 병렬 분석 수, 제한 시간, Jira API 버전·issue type·필수 커스텀 필드 등 |

설정 파일로 관리하려면 프로젝트 루트에서 실행하세요.

```sh
.venv/bin/python scripts/configure.py validate config/examples/settings.json
.venv/bin/python scripts/configure.py export my-settings.json
# my-settings.json을 편집한 뒤
.venv/bin/python scripts/configure.py validate my-settings.json
.venv/bin/python scripts/configure.py import my-settings.json
```

샘플은 [config/examples/settings.json](config/examples/settings.json)입니다. `validate`는 형식 검사이며 실제 인증·실행 성공을 보장하지 않습니다. 비밀번호와 토큰 값은 JSON에 넣지 않고 실행 서버의 인증 환경에 설정하세요. 예를 들어 `jira_auth_env`는 토큰 값이 아닌 `BSP_JIRA_TOKEN` 같은 환경변수 이름입니다. Jira 인증 환경은 API와 worker 양쪽에 전달해야 합니다.

실제 모드는 같은 서버에서 동작하는 JSON stdin/stdout 브리지 계약을 사용합니다. 설치된 도구의 실행·세션·리뷰 결과를 이 계약에 맞추는 wrapper가 필요합니다. 실제 도구 전용 wrapper는 아직 포함하지 않았습니다. [실행 어댑터](backend/adapters/bridge.py), [Jira 어댑터](backend/adapters/jira.py), [연동 설계](docs/design/API_AND_INTEGRATIONS.md)를 참고하세요.

## 4. 작업 진행 순서

1. **새 업그레이드**에서 이름과 접속 모드를 정하고 **분석 시작**을 누릅니다.
2. 모든 모듈이 부트로더 완료와 무관하게 분석됩니다. 분석 동시 수는 설정으로 제한합니다.
3. 전체 분석 후 **계획 검토 · 확인 → 이 계획으로 진행**을 누릅니다. 이 확인 전에는 선행 모듈도 설계 이후로 진행하지 않습니다.
4. 선행 그룹이 설계 → 코드 구현 → 빌드 → 검증 → 장비 테스트를 진행합니다. 수정과 빌드는 같은 작업 폴더에서 순차 실행합니다.
5. 모듈 행을 펼쳐 단계별 상태·산출물·이력을 확인하고 수동시험 결과를 등록합니다. 선행 그룹 **전체**가 완료되면 나머지 모듈의 설계 이후 작업이 시작됩니다.
6. 실패한 단계의 **재시도**를 누르면 새 실행이 생성되고 이전 실패 이력은 남습니다. 수동시험 재시도는 새 결과 대기이며 자동 장비 시험이 아닙니다.
7. 모든 모듈 완료 후 통합 검증과 **최종 검토 기록**을 마치면 작업 전체가 완료됩니다. 종합 진행도의 단계별 100%와 최종 완료는 별도로 관리합니다.

상단 **종합 진행도**는 요구사항 분석 / 구현(설계+코드) / 검증 / 빌드 / 테스트를 집계합니다. 실제 실행 순서는 모듈의 여섯 단계가 기준입니다.

### 수동시험 결과 등록

모듈을 펼치고 장비 테스트의 **결과 등록**을 누릅니다. **각 시험의 PASS/FAIL만 필수**입니다. 현재 기본 시험은 `boot`, `functional` 두 개입니다.

- 모두 PASS이면 해당 장비 테스트가 완료됩니다. 하나라도 FAIL이면 실패로 기록합니다.
- **추가 정보 (선택)**을 펼치면 보드 ID, 수행자, 수행 시각, 이미지 SHA-256, 근거 파일을 입력할 수 있습니다. 모두 비워도 등록됩니다.
- 작업·현재 실행·이미지·소스·시험 계획·등록 시각은 서버가 자동 연결합니다. 미입력한 수행자나 실제 수행 시각을 임의로 채우지 않습니다.
- 추가 정보를 입력했다면 유효한 값이어야 합니다. 다른 이미지의 해시, 오래된 시험 계획, 잘못된 시각·파일은 거부합니다. 첨부 파일은 최대 2MB입니다.
- 결과를 등록해도 최종 사람 검토는 별도로 남습니다.

### 데모에서 선행 모듈 수동 완료

최초 계획 확인 후 `Bootloader`, `Kernel / BSP` 등 **선행 그룹의 모듈 행을 펼치고 「데모에서 이 모듈 완료」**를 누르세요. 해당 모듈의 남은 단계를 모의 완료로 기록합니다. 선행 모듈이 여러 개면 각각 완료해야 나머지 그룹이 진행합니다.

이 버튼은 데모 작업의 선행 그룹에만 제공됩니다. 실제 실행 모드에서는 서버도 요청을 거부합니다. 최초 계획 미확인·일시 중지·관련 사람 판단 대기 중에는 사용할 수 없습니다. 실행 중이던 데모 이력과 실패 이력은 보존하며 뒤늦은 결과로 완료 상태를 덮어쓰지 않습니다. 최종 검토는 생략되지 않습니다.

### 질문·판단·Jira

**작업 명령**에서 대상과 의도를 선택해 질문, 실패 재시도, 일시 중지·재개, 메모를 요청할 수 있습니다. 데모 질문 응답은 모의 응답으로 표시합니다. 프롬프트가 실행 게이트를 임의로 해제하지 않습니다.

새 판단이 필요하면 내부 판단 항목에 기록합니다. 관련 모듈만 대기하고 독립 작업은 계속됩니다. 실제 모드에서 Jira 연결이 설정된 경우 worker가 외부 티켓 연결을 시도합니다. Jira 결정 완료와 코드에 반영된 상태는 구분합니다. 연결 확인의 읽기 성공은 티켓 생성 권한 확인을 뜻하지 않습니다.

## 5. 데이터와 문제 해결

작업·설정·명령·이력은 `.runtime/dashboard.db`, 산출물과 선택 첨부는 `.runtime/artifacts/`, 접속 키는 `.runtime/access-token`에 저장합니다. `.runtime/`, `.venv/`, `node_modules/`, 빌드 파일과 로컬 시험 자료는 Git에서 제외합니다. 실행 중 DB를 단순 복사하기보다 SQLite 백업 기능과 산출물 보존을 함께 사용하세요.

| 증상 | 확인할 항목 |
|---|---|
| 화면이 열리지 않음 | UI 빌드, API 포트, Windows의 SSH 터널과 서버 실행 여부 |
| 접속 키가 맞지 않음 | 접속 대상 서버와 runtime의 키인지 확인 |
| 상태가 진행되지 않음 | worker 실행 여부, 최초 계획 확인, 일시 중지, 선행 그룹과 사람 판단 대기 |
| 설정을 바꿨는데 기존 작업은 그대로임 | 설정은 새 작업부터 적용. 기존 작업 기준은 고정 |
| 재시작 후 UNKNOWN 표시 | 실제 프로세스 상태 확인 전 재시도를 차단한 상태. 데모는 화면의 모의 실행 복구 기능 사용. 실제 프로세스 자동 재연결은 미구현 |
| 선행 그룹이 모두 완료되지 않음 | 선행 그룹에 포함된 모든 모듈 확인. Bootloader 하나만 완료해도 다른 선행 모듈이 남을 수 있음 |
| 브리지·Jira 확인 실패 | 실제 서버의 실행 파일·인증 환경·사내망·계약 확인. 등록만으로 연결 성공 처리하지 않음 |

## 6. 개발 검증과 남은 범위

```sh
.venv/bin/python -m pytest -q
npm run build --prefix apps/web
# Playwright Chromium이 준비된 환경에서 실행
.venv/bin/python scripts/test_e2e.py
```

브라우저 시험은 매번 별도 runtime을 만들고 기본 `8766` 포트를 사용합니다. 포트 사용 중이면 다른 서버에 붙지 않고 종료합니다. `BSP_E2E_PORT=18766`으로 시험 포트를 바꿀 수 있습니다. 설치된 브라우저를 사용하려면 `BSP_BROWSER_EXECUTABLE`에 실행 파일의 절대 경로를 지정하세요. 최신 결과와 실패·재시험 이력은 [작업 진행 기록](docs/implementation/WORK_STATUS.md)과 [시험 실행 기록](docs/testing/runs/README.md)을 참고하세요.

현재 한계는 실제 CLI wrapper·Linux/SSH·보드·사내 Jira 검증, 자동 보드팜, 정교한 모듈 의존 그래프, 변경 영향 범위 계산, 다중 이미지 묶음, 모듈 계획 편집, 다중 사용자 권한과 운영 서비스 설치입니다. 실제 환경의 전체 인수를 완료한 제품으로 간주하지 않습니다.

## 개발·검토 문서

- Codex 구현 지침: [AGENTS.md](AGENTS.md)
- Claude 검토 지침: [CLAUDE.md](CLAUDE.md)
- 요구사항·구조·상세 설계: [docs/README.md](docs/README.md)
- 테스트 계획과 결과: [TEST_PLAN.md](docs/testing/TEST_PLAN.md)
