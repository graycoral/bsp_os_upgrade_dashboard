# Windows에서 GUI Test만 빌드하기

이 가이드는 Windows에서 **GUI Test 단독 웹 프로그램**을 빌드하고 다른 Windows PC에 설치하는 절차입니다. `gui_test/`의 Python 모듈과 웹 화면만 빌드하며, 기존 Dashboard 서버·Worker·`apps/web` 빌드는 실행하지 않습니다.

현재 실행은 Mock TC/RBM 기반입니다. 빌드 성공은 실제 COM 장비·Linux TC·사내 RBM 연동 검증을 의미하지 않습니다. 기존 Dashboard에 통합하려면 [통합 안내](../../gui_test/README.md#기존-dashboard에-통합)를 별도로 따릅니다.

## 1. 빌드 PC 준비

| 항목 | 빌드하는 PC | 완성된 ZIP을 설치하는 PC |
|---|---|---|
| 운영체제 | Windows 10/11 x64 | Windows 10/11 x64 |
| Python | **CPython 3.12 x64** | **CPython 3.12 x64** |
| Node.js / npm | **Node.js 22.12 이상인 22.x**, 포함된 npm | 불필요 |
| PowerShell | Windows PowerShell 5.1 또는 PowerShell 7 | 설치 명령 실행에 사용 |
| Git | 저장소 clone 시에만 필요. 소스 ZIP이면 불필요 | 불필요 |
| 네트워크 | npm/Python 의존성 다운로드용 인터넷 또는 승인된 사내 미러 | 의존성이 포함된 ZIP이면 불필요 |
| 브라우저 | Edge 또는 Chrome | Edge 또는 Chrome |

Python·Node.js 설치 후 새 PowerShell을 열어 확인합니다.

```powershell
py -3.12 --version
py -3.12 -c "import platform, struct; print(platform.machine(), struct.calcsize('P') * 8)"
node --version
npm.cmd --version
```

Python은 `3.12.x`, 비트 수는 `64`여야 합니다. ARM64·32비트 Python과 다른 Python minor 버전은 이 Windows 배포 묶음의 대상이 아닙니다. 설치 파일에는 Python 자체가 포함되지 않습니다.

## 2. 소스 준비

저장소를 clone하거나 GitHub에서 소스 ZIP을 내려받아 압축을 풉니다. 아래 예시는 저장소가 `C:\work\bsp_os_upgrade_dashboard`에 있는 경우입니다.

**`gui_test/` 폴더만 복사해도 단독 빌드할 수 있습니다.** 이때 폴더 내부의 `web/package.json`, `web/package-lock.json`, 웹 설정 파일, `pyproject.toml`, `requirements.lock`, `standalone/` 등을 모두 보존하세요. Dashboard의 `backend/`, `apps/`, 루트 `requirements.lock`이나 Git 이력은 단독 빌드에 필요하지 않습니다. 폴더 이름 `gui_test`도 유지합니다.

## 3. 한 번에 빌드

저장소 루트에서 실행합니다.

```powershell
cd C:\work\bsp_os_upgrade_dashboard
.\gui_test\standalone\build.ps1
```

`gui_test/` 폴더만 복사한 경우에는 그 폴더에서 실행합니다.

```powershell
cd C:\work\gui_test
.\standalone\build.ps1
```

Python launcher(`py`)가 없거나 Python 경로를 명시하려면:

```powershell
.\gui_test\standalone\build.ps1 -PythonExecutable "C:\Python312\python.exe"
```

전역 Python 환경이나 기존 Dashboard 가상환경을 활성화할 필요는 없습니다. 스크립트는 전용 빌드 가상환경을 사용합니다. 기존 테스트 DB와 `%LOCALAPPDATA%\GuiTest`의 실행 데이터는 빌드 대상이 아닙니다.

PowerShell 실행 정책으로 `.ps1`이 차단되면 사내 승인된 서명/실행 절차를 사용하세요. 스크립트와 `build.cmd`는 실행 정책을 자동 변경하지 않습니다. 명령 프롬프트에서는 다음 진입점을 사용할 수 있으며, 동일한 PowerShell 정책이 적용됩니다.

```bat
gui_test\standalone\build.cmd
```

공백이 있는 경로는 따옴표로 감쌉니다. 실행 위치와 관계없이 스크립트 자신의 위치에서 `gui_test/`를 찾습니다.

### 빌드 과정

1. Windows·Python 3.12 x64·Node 22.12+의 22.x·npm을 확인합니다.
2. `gui_test/.build/venv`에 전용 가상환경을 준비하고 잠긴 Python 의존성을 설치합니다.
3. `gui_test/web`에서 `npm ci` 후 `npm run build`를 실행합니다. GUI Test 전용 TypeScript 검사와 Vite 빌드 결과는 `gui_test/static/`에 저장됩니다.
4. GUI Test 단독 시험을 실행하고 Python wheel을 생성합니다.
5. 설치된 wheel로 단독 Mock E2E를 확인합니다.
6. 기본적으로 Windows Python 3.12용 의존성 wheel을 내려받고 단독 배포 ZIP을 생성합니다.

각 외부 명령이 실패하면 즉시 중단하고 0이 아닌 종료 코드를 반환합니다. 중간 산출물이 남아 있어도 실패한 빌드 결과를 배포하지 마세요. 기존 Dashboard 전체 회귀 시험과 Dashboard 연동 E2E는 단독 빌드의 범위에 포함하지 않으며, 저장소 CI에서 별도로 수행합니다.

### 선택 옵션

| 옵션 | 용도 |
|---|---|
| `-PythonExecutable "C:\Python312\python.exe"` | Python 실행 파일을 직접 지정. 미지정 시 `py -3.12` 사용 |
| `-OutputDirectory "C:\build output\GuiTest"` | 산출물 폴더 지정. 기본값 `gui_test/dist` |
| `-SkipWheelhouse` | 의존성 wheel 다운로드 생략. 실행 PC에서 온라인/사내 미러 설치 필요 |
| `-SkipTests` | 빌드 과정의 시험 생략. 검증되지 않은 산출물임을 명시하고 사용 |

예시:

```powershell
.\gui_test\standalone\build.ps1 -OutputDirectory "C:\build output\GuiTest"
```

기본 빌드는 의존성을 다운로드합니다. `-SkipWheelhouse`는 **오프라인 빌드 옵션이 아닙니다**. npm 설치와 Python 빌드 환경 준비에는 여전히 패키지 저장소 접근이 필요합니다. 사내 미러 사용 시 기존 npm/pip 설정으로 승인된 저장소를 지정하며, 인증정보를 소스나 로그에 기록하지 않습니다.

## 4. 산출물

기본 출력 위치는 `gui_test/dist/`입니다.

| 파일·폴더 | 내용 |
|---|---|
| `gui-test-windows-py312.zip` | 다른 Windows PC에 전달할 단독 프로그램 묶음 |
| `wheels/bsp_gui_test-*.whl` | 미리 빌드된 웹 화면을 포함한 Python 패키지 |
| `wheelhouse/` | Python 3.12 x64용 의존성 wheel. `-SkipWheelhouse`이면 생략 |
| `build-info.json` | 빌드 환경·옵션 등 확인 정보 |
| `tests.xml`, `demo-e2e.json` | 기본 빌드에서 실행한 시험 증거. `-SkipTests`이면 생성되지 않음 |

ZIP 안에는 `gui_test/`, `wheels/`, `wheelhouse/`(기본 빌드), `INSTALL.md`, `SHA256SUMS.json`이 들어갑니다. `backend/`, `apps/`, Dashboard 통합 patch는 포함하지 않습니다. 런타임 DB·로그·가상환경·`node_modules`도 배포하지 않습니다.

**이 ZIP은 Python 없이 실행하는 단일 EXE가 아닙니다.** 실행 PC에도 Python 3.12 x64가 필요합니다. 설치 후 생기는 `gui-test.exe`는 해당 Python 가상환경의 명령 진입점입니다.

## 5. 실행 PC에서 오프라인 설치·실행

ZIP을 새 폴더(예: `C:\GuiTest`)에 풀고 PowerShell에서 실행합니다. 이 폴더 바로 아래에 `gui_test`, `wheels`, `wheelhouse`가 있어야 합니다.

```powershell
cd C:\GuiTest
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --no-index --find-links .\wheelhouse -r .\gui_test\requirements.lock
$wheel = Get-ChildItem .\wheels\bsp_gui_test-*.whl | Select-Object -First 1
.\.venv\Scripts\python.exe -m pip install --no-index --no-deps $wheel.FullName
.\.venv\Scripts\gui-test.exe start --runtime "$env:LOCALAPPDATA\GuiTest" --port 8767
Start-Process http://127.0.0.1:8767
```

각 명령의 성공을 확인한 뒤 다음 명령을 실행합니다. 별도 가상환경 활성화 스크립트는 필요하지 않습니다. 설치 후 `python.exe -m pip check`로 의존성 충돌도 확인할 수 있습니다.

`-SkipWheelhouse`로 빌드했다면 위 의존성 설치 한 줄을 아래로 바꿉니다. 이 경우 실행 PC에서 인터넷 또는 승인된 사내 미러에 접근할 수 있어야 합니다.

```powershell
.\.venv\Scripts\python.exe -m pip install -r .\gui_test\requirements.lock
```

GUI Test 단독 포트는 **8767**입니다. 기존 Dashboard의 8765와 구분됩니다. Mock 데모에서는 실제 보드를 연결하지 않아도 TC 선택·전체 PASS·FAIL 후 계속·연결 오류와 재개·리포트 생성을 확인할 수 있습니다.

상태 확인과 종료:

```powershell
.\.venv\Scripts\gui-test.exe status --runtime "$env:LOCALAPPDATA\GuiTest" --port 8767
.\.venv\Scripts\gui-test.exe stop --runtime "$env:LOCALAPPDATA\GuiTest" --port 8767
```

브라우저를 닫아도 서비스는 계속 실행됩니다. 종료 명령을 사용하세요. 재시작은 같은 runtime·port로 `restart`를 실행하며, 업그레이드는 실행 중 시험을 정리한 뒤 정지→데이터 백업→새 wheel 설치→시작 순서로 수행합니다.

## 6. 다시 빌드하기와 검증 범위

코드를 수정한 뒤 같은 `build.ps1` 명령을 다시 실행합니다. 실행 중인 서비스는 wheel 재설치와 재시작을 해야 새 Python 코드를 사용합니다. 웹 화면도 새 wheel의 정적 파일을 사용하도록 업데이트한 뒤 브라우저를 새로고침합니다.

단독 빌드의 시험은 GUI Test 코어/API/패키징과 설치된 wheel의 Mock E2E에 집중합니다. Git 저장소 탐색 및 Dashboard 엔진이 필요한 시험은 전체 저장소 회귀에서 수행합니다. 두 범위의 결과를 혼동하지 마세요. `-SkipTests` 산출물을 시험 통과로 표시하지 않습니다.

Windows CI는 동일한 빌드 진입점을 사용하며, 산출물 설치 후 서비스 시작·상태·화면 응답·종료를 확인합니다. CI 결과와 산출물은 해당 커밋의 GitHub Actions 실행을 확인하세요. 실제 Windows COM 연결·Linux TC·회사 RBM·운영 Dashboard 쓰기는 후속 현장 검증 대상입니다.

## 7. 문제 해결

| 증상 | 확인·조치 |
|---|---|
| `py`를 찾을 수 없음 | Python 3.12 x64를 설치하거나 `-PythonExecutable`로 실행 파일 지정 |
| Python 버전/아키텍처 검사 실패 | ARM64/32비트나 다른 minor가 아닌 CPython 3.12 x64 선택 |
| `node`/`npm.cmd` 없음 | Node 22.12+의 22.x 설치 후 PowerShell 새로 열기 |
| `.ps1` 실행 차단 | 조직 정책에 맞는 서명/승인 절차 적용. `build.cmd`도 정책을 우회하지 않음 |
| npm/pip 다운로드 실패 | 프록시·사내 미러·인증서·접근 허용 확인. TLS 검증을 끄지 않음 |
| `npm ci`의 lock 불일치 | 의도한 의존성 변경을 검토한 뒤 `gui_test/web`에서 lock을 갱신하고 재검증. 빌드 스크립트는 자동 갱신하지 않음 |
| 공백 경로에서 실패 | 스크립트/옵션의 전체 경로를 따옴표로 감싸고 Python 실행 파일 경로를 확인 |
| wheel 설치 후 화면 없음 | 최신 빌드의 wheel인지, `gui_test/static/index.html`이 생성됐는지 확인 |
| 포트가 이미 사용 중 | 기존 GUI Test를 같은 runtime·port로 정지하거나 `--port 8877` 등 다른 포트를 모든 명령에 동일하게 적용 |
| 서비스 시작 실패 | `Get-Content "$env:LOCALAPPDATA\GuiTest\service.log" -Tail 100`으로 원인 확인 |

문제를 전달할 때 실행한 명령, Python/Node 버전, 처음 실패한 단계와 오류 메시지를 함께 남깁니다. 사내 주소·토큰·계정·실장비 식별정보는 가리고 공유합니다.
