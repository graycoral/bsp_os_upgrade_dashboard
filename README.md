# BSP OS Upgrade Dashboard

BSP OS 업그레이드의 모듈 분석·구현·빌드·검증·수동 장비 시험과 사람의 판단을 관리하는 웹 대시보드입니다.

현재는 **로컬에서 검증한 1차 구현**입니다. 기본 설정으로 외부 서비스 없이 데모를 실행할 수 있습니다. Linux 작업 폴더에서 설치된 Claude/OpenCode/Codex를 실행하는 내장 연결을 제공합니다. 별도 브리지 제작은 필요하지 않으며 실제 Linux·모델·BSP 빌드·사내 Jira 인수는 아직 별도입니다. 데모의 산출물은 시연용 JSON이며 보드에 적용할 OS 이미지가 아닙니다.

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

브라우저에서 `http://127.0.0.1:8765`를 열면 **키 입력이나 로그인 없이 바로 대시보드**가 표시됩니다. `.runtime/access-token`은 더 이상 만들거나 읽지 않습니다. 이전 버전의 파일이 남아 있어도 사용하지 않습니다. 화면을 여는 것만으로 업그레이드를 자동 시작하지는 않으며, **새 업그레이드** 버튼으로 작업을 시작합니다.

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

Windows 브라우저에서 `http://127.0.0.1:8765`를 열면 바로 대시보드에 접속됩니다. SSH 접속 인증 외에 대시보드 키 입력은 없습니다. 포트가 겹치면 스크립트에 `-LocalPort 8877`을 주고 해당 주소를 여세요. SSH 터널을 닫아도 서버의 API·worker가 살아 있으면 작업 기록과 실행은 유지됩니다.

현재는 두 접속 방식 모두 장비 시험을 사람이 수행합니다. Windows에서 이미지를 내려받아 로컬 장비를 시험하거나 Linux 환경에서 수동 시험한 후 같은 화면에 결과를 등록합니다. 자동 플래시와 보드팜 연결은 후속 범위입니다.

서버는 `127.0.0.1`에만 열고 로컬 연결과 SSH 터널 접속을 허용합니다. 다른 웹사이트에서 들어오는 API 요청과 임의 폼 제출은 차단합니다. 대시보드의 단일 운영자 사용 방식이며, Jira와 에이전트의 외부 서비스 인증은 각 설정대로 유지됩니다.

## 3. 환경 설정

왼쪽 **환경 설정**에서 값을 입력하고 **설정 저장**을 누르세요. JSON 파일 가져오기·내보내기도 지원합니다. 저장한 설정은 **새 작업부터 적용**되며 기존 작업의 실행 모드와 소스 기준을 바꾸지 않습니다.

| 설정 | 사용 방법 |
|---|---|
| 실행 방식 | 처음에는 `demo`. 실제 환경 설정 후 실제 Linux 실행(`bridge`) 선택 |
| Linux 호스트·계정 | 연결 대상 표시 정보. 입력만으로 원격 SSH 실행이 시작되지는 않음 |
| 작업 폴더 | worker가 실행되는 서버의 실제 작업 디렉터리 |
| 소스 기준 | 세 소스 경로를 지정. 커밋/해시는 선택 입력이며 빈칸이면 새 작업 시작 때 신규 OS 원본의 Git HEAD 자동 기록 |
| 도구 연결 방식 | `native` 기본. 설치된 도구를 PATH에서 자동 탐지. 기존 JSON 브리지는 고급 호환 설정 |
| 에이전트 지침 폴더 | 다른 프로젝트의 역할 지침 위치. 빈칸은 작업 폴더. 기존 파일은 읽기만 함 |
| 빌드·검증 | 기존 빌드 명령, 산출물 파일, 검증 명령, 통합·회귀 명령. 필요하면 환경 초기화 파일 |
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

외부에서 만든 모듈 에이전트 담당자에게는 **[에이전트 상태·결과 보고 계약](docs/design/AGENT_STATUS_CONTRACT.md)**을 전달하세요. 필수 보고 데이터, 단계별 성공/실패·빌드·리뷰 JSON 예시, 연결 절차를 한 문서에서 관리합니다. 현재는 단계 종료 결과를 받아 화면을 갱신하며 실행 중 세부 진행률·heartbeat 수신은 아직 지원하지 않습니다.

**저장 후 환경 점검**으로 도구·필수 옵션·로그인 설정을 확인하세요. CLI_READY는 실제 모델 호출 성공을 뜻하지 않습니다. 로그인은 Linux의 같은 계정에서 도구별로 준비합니다. 모듈 결과 변환은 내장 어댑터가 처리하며 사용자 wrapper는 필요하지 않습니다. 상세 입력·실행·이전 설정 호환은 [작업 폴더 기반 연결 안내](docs/agents/ENVIRONMENT_AND_BRIDGES.md)를 따릅니다. Jira는 별도 [Jira 어댑터](backend/adapters/jira.py), [연동 설계](docs/design/API_AND_INTEGRATIONS.md)를 참고하세요.

### Claude에서 직접 사용하는 오케스트레이터

[Claude 사용 안내](docs/agents/CLAUDE_ORCHESTRATOR_GUIDE.md)와 [실제 agent 정의](.claude/agents/bsp-upgrade-orchestrator.md)를 추가했습니다. 이 프로젝트 폴더에서 Claude를 열고 `bsp-upgrade-orchestrator`와 입력 JSON 경로를 지정하면 검토용 제안을 요청할 수 있습니다. 실제 Claude 호출은 사용자가 진행합니다.

```bash
python3 scripts/claude_orchestrator.py check-agent
python3 scripts/claude_orchestrator.py validate --request examples/claude-orchestrator/request.json --result examples/claude-orchestrator/result.example.json --workspace examples/claude-orchestrator
python3 scripts/claude_orchestrator.py export --output /path/to/new-bsp-orchestrator
```

입력·결과 검사와 다른 서버에 옮길 패키지를 제공합니다. 예시는 가상 작업이며 도구는 제안을 실행하지 않습니다. 기존 폴더에 덮어쓰지 않습니다.

### 대시보드 자동 연동 설계

작업별 Claude 오케스트레이터가 모듈 결과를 종합하고 계획·재작업·새 판단을 제안하며, 기존 서버가 실행 조건을 검사해 실제 배정과 상태 저장을 맡도록 설계했습니다. 모듈 보고는 서버에 먼저 저장하므로 조정 세션이 끊겨도 이력을 유지합니다.

**대시보드의 자동 조정·제안 적용·보고 v2는 아직 구현 전입니다.** 위 수동 호출 패키지와 구분합니다. 현재는 조정 세션 연결/질문과 모듈 보고 v1을 사용합니다. 외부 에이전트 담당자는 [오케스트레이터 명세](docs/design/ORCHESTRATOR_SPEC.md)와 [모듈 보고 계약의 v2 설계](docs/design/AGENT_STATUS_CONTRACT.md)를 함께 확인하세요. 신규 orchestrate 호출·v2 보고·새 설정은 서버와 wrapper 구현/시험을 마친 뒤 사용합니다. 실시간 세부 퍼센트와 heartbeat는 이번 확장 범위에도 포함되지 않습니다.

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

작업·설정·명령·이력은 `.runtime/dashboard.db`, 산출물과 선택 첨부는 `.runtime/artifacts/`에 저장합니다. `.runtime/`, `.venv/`, `node_modules/`, 빌드 파일과 로컬 시험 자료는 Git에서 제외합니다. 실행 중 DB를 단순 복사하기보다 SQLite 백업 기능과 산출물 보존을 함께 사용하세요.

| 증상 | 확인할 항목 |
|---|---|
| 화면이 열리지 않음 | UI 빌드, API 포트, Windows의 SSH 터널과 서버 실행 여부 |
| 이전 로그인 화면이 보임 | 최신 UI를 다시 빌드하고 API를 재시작한 뒤 브라우저 새로고침 |
| 상태가 진행되지 않음 | worker 실행 여부, 최초 계획 확인, 일시 중지, 선행 그룹과 사람 판단 대기 |
| 설정을 바꿨는데 기존 작업은 그대로임 | 설정은 새 작업부터 적용. 기존 작업 기준은 고정 |
| 재시작 후 UNKNOWN 표시 | 실제 프로세스 상태 확인 전 재시도를 차단한 상태. 데모는 화면의 모의 실행 복구 기능 사용. 실제 프로세스 자동 재연결은 미구현 |
| 선행 그룹이 모두 완료되지 않음 | 선행 그룹에 포함된 모든 모듈 확인. Bootloader 하나만 완료해도 다른 선행 모듈이 남을 수 있음 |
| 도구·Jira 확인 실패 | 실제 서버의 실행 파일·인증 환경·사내망·계약 확인. 등록만으로 연결 성공 처리하지 않음 |

## 6. 개발 검증과 남은 범위

```sh
.venv/bin/python -m pytest -q
npm run build --prefix apps/web
# Playwright Chromium이 준비된 환경에서 실행
.venv/bin/python scripts/test_e2e.py
```

브라우저 시험은 매번 별도 runtime을 만들고 기본 `8766` 포트를 사용합니다. 포트 사용 중이면 다른 서버에 붙지 않고 종료합니다. `BSP_E2E_PORT=18766`으로 시험 포트를 바꿀 수 있습니다. 설치된 브라우저를 사용하려면 `BSP_BROWSER_EXECUTABLE`에 실행 파일의 절대 경로를 지정하세요. 최신 결과와 실패·재시험 이력은 [작업 진행 기록](docs/implementation/WORK_STATUS.md)과 [시험 실행 기록](docs/testing/runs/README.md)을 참고하세요.

현재 한계는 실제 Linux CLI·인증·Linux/SSH·보드·사내 Jira 검증, 자동 보드팜, 정교한 모듈 의존 그래프, 변경 영향 범위 계산, 다중 이미지 묶음, 모듈 계획 편집, 다중 사용자 권한과 운영 서비스 설치입니다. 실제 환경의 전체 인수를 완료한 제품으로 간주하지 않습니다.

## 개발·검토 문서

- Codex 구현 지침: [AGENTS.md](AGENTS.md)
- Claude 검토 지침: [CLAUDE.md](CLAUDE.md)
- 요구사항·구조·상세 설계: [docs/README.md](docs/README.md)
- 테스트 계획과 결과: [TEST_PLAN.md](docs/testing/TEST_PLAN.md)

### 소스 기준 자동 기록과 내장 도구 연결

고정 기준은 결과 추적을 위해 작업마다 남기지만 **설정에서 커밋/해시를 직접 입력할 필요는 없습니다.** 빈칸이면 신규 OS 원본의 깨끗한 Git HEAD를 새 작업에 자동 기록합니다. 데모는 시연용 기준을 자동 사용합니다. Git이 아닌 고정 소스 묶음은 해시를 직접 지정합니다.

내장 연결에서는 작업 폴더와 프로젝트의 빌드/시험 명령을 설정하면 됩니다. 브리지 경로 입력은 고급 호환 모드에만 남깁니다. 코드 수정 후에는 실제 파일 내용 해시를 별도로 기록하고 교차 리뷰와 연결합니다. [설정·연결 안내](docs/agents/ENVIRONMENT_AND_BRIDGES.md)에서 설정 예시와 한계를 확인하세요.

## GUI Test 프로그램 (Mock Adapter 기반)

좌측 **Test 현황**에서 TC 선택, Single/Dual 보드·COM 프로파일, 순차 실행, 정지·재개·취소, 로그와 PDF/HTML/CSV/JSON 리포트를 사용할 수 있습니다. Windows 단독 웹 GUI는 기존 Dashboard 없이도 실행됩니다. 전체 Run 종료 뒤 별도 데모 Job의 모듈 결과를 반영하며 기존 운영 Job/수동 시험/게이트를 보존합니다.

[Windows 설치·실행·오프라인 반입·Dashboard 통합·실제 Adapter 연결 안내](gui_test/README.md) / [검증 기록](gui_test/VALIDATION.md)

GUI Test만 Windows에서 빌드하려면 `gui_test\standalone\build.ps1`을 실행하세요. [전용 빌드 가이드](docs/gui_test/WINDOWS_BUILD.md)에 Python/Node 준비, 단독 ZIP 생성과 설치 절차가 있습니다. 기존 Dashboard 서버·Worker의 Windows 지원 범위와 별개이며, 단독 GUI Test 빌드에는 `apps/web` 빌드가 필요하지 않습니다.

실제 TC 명령과 사내 RBM API는 아직 연결하지 않았습니다. 데모 결과는 실장비 검증이 아니며 운영 `device_test`를 변경하지 않습니다.
