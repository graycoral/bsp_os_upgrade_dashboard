# GUI Test 프로그램

기존 BSP Dashboard를 보존하면서 `gui_test/`에 분리한 테스트 실행 모듈입니다. **현재 배포는 Mock Adapter 기반 데모입니다.** 회사 TC 원본, 내부 RBM 주소, 계정, 토큰, 실제 보드 정보는 포함하지 않습니다. 실제 TC 명령의 COM 옵션과 사내 API가 확정되면 Adapter를 연결해야 하며, 이 버전을 실장비 시험 완료로 사용하면 안 됩니다.

## 지원 범위

| 기능 | 구현 |
|---|---|
| Windows 단독 웹 GUI | 로컬 FastAPI + 백그라운드 관리자 + SQLite, Dashboard 없이 실행 |
| Dashboard 통합 | 기존 메뉴 `Test 현황`, 동일 React 화면·Core, 기존 Linux Worker 사용 |
| TC | 읽기 전용 폴더/Git 탐색 Core, `dual` 폴더 분류, 안정 ID/소스 해시, 검색·필터·폴더/개별 선택, 순서·Suite 저장 |
| 연결 | Single A / Dual A+B, 같은 호스트·서로 다른 보드/COM 검증, 프로파일 저장, 수동 입력 대체 |
| 실제 Windows COM | `pyserial` OS 열거, 단독 화면에서 조회. 실제 보드 식별/TC 실행은 미연동 |
| 실행 | 순차, FAIL 후 계속, 환경 ERROR/Timeout 일시 정지, 사용자 복구·재개, 취소, 종료 불명 UNKNOWN |
| 상태 | Run/Attempt 분리, 진행률 = 유효 PASS+FAIL / 전체 TC, 완료 Run 불변, 재검증은 새 Run |
| 예약/제어 | 보드+COM 원자 예약, 정지 중 유지, 종료 확인 뒤 해제, 브라우저 제어권 요청/승인/명시적 만료 인수 |
| 결과 | 정확한 `Test Result: PASS\|FAIL` + 종료 코드 검사, 실시간 로그, 모든 Attempt·감사 이력 |
| 내보내기 | PDF / HTML / CSV / JSON, 전체 ZIP 로그, Attempt별 stdout/stderr |
| Dashboard 결과 | 전체 Run PASS/FAIL 뒤 필수 사례별 집계, 모듈 독립 결과, 멱등 outbox, 이미지/계획/Attempt 기준 검사 |
| 완료 Job 재검증 | 자동 결과 새 Attempt, 과거 수동 결과/최종 검토 보존, 통합 결과 무효화, 재검증 승인 게이트 |
| 안전 경계 | loopback, Host/Origin/Fetch-Site/변경 헤더 검사, 2 MB 입력 제한, 로그 한도/일반 secret 키 마스킹 |

**모드 분리:** Windows 단독 Run은 Dashboard와 공유하지 않습니다. Dashboard Mock Run은 `gui-test-dashboard-demo/` 아래 별도 DB의 Job만 변경합니다. 기존 `dashboard.db`의 Job을 선택하거나 자동 덮어쓰는 기능은 활성화하지 않았습니다. 일반 TC 실행은 Job 없이 가능합니다.

## 회사 Windows 설치 — GitHub/Node.js 없이

권장 대상: **Windows 10/11 x64, Python 3.12 x64**, 최신 사내 승인 Edge/Chrome. 관리자 권한은 기본적으로 필요하지 않습니다. Python 설치 자체는 사내 배포 절차를 따릅니다.

GitHub Actions의 `GUI-Test-Windows-Python312` artifact 또는 `package.py`로 만든 `gui-test-company.zip`을 승인된 경로로 반입해 압축을 풉니다. ZIP에는 공용 소스, 미리 빌드한 웹 UI, Python wheel, Windows Python 3.12용 의존성 wheelhouse, 최소 통합 patch, SHA256 목록이 포함됩니다. `wheelhouse/`가 없는 source-only ZIP은 아래 온라인/사내 미러 설치 또는 반입 PC에서 wheelhouse 준비가 필요합니다.

PowerShell, ZIP을 푼 폴더에서:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --no-index --find-links .\wheelhouse -r .\gui_test\requirements.lock
$wheel = Get-ChildItem .\wheels\bsp_gui_test-*.whl | Select-Object -First 1
.\.venv\Scripts\python.exe -m pip install --no-index --no-deps $wheel.FullName
.\.venv\Scripts\gui-test.exe start --runtime "$env:LOCALAPPDATA\GuiTest" --port 8767
Start-Process http://127.0.0.1:8767
```

브라우저를 닫아도 실행은 계속됩니다. 단독 GUI는 Dashboard·RBM 연결 없이 Mock 실행 가능하며, 실제 Windows→Linux TC 연결 시에는 기존 Linux 서버가 필요합니다. 동일 Windows 호스트에서 **단독/통합 실장비 Run을 동시에 실행하지 마세요.** 현재 모드별 논리 예약은 공통 물리 COM 잠금을 보증하지 않으므로 실장비 실행은 차단돼 있습니다.

온라인 또는 승인된 사내 Python 미러를 사용할 경우:

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r .\gui_test\requirements.lock
.\.venv\Scripts\python.exe -m pip install --no-build-isolation --no-deps .\gui_test
.\.venv\Scripts\gui-test.exe start --runtime "$env:LOCALAPPDATA\GuiTest" --port 8767
```

소스에서 설치할 때도 `gui_test/static/index.html`이 있어야 합니다. 회사 Windows에 Node.js를 설치하지 않으려면 외부 빌드 PC에서 UI를 빌드한 ZIP/wheel을 사용하세요. Python 3.11/3.13 또는 ARM64는 해당 플랫폼용 wheelhouse를 별도로 준비하고 재검증해야 합니다. 제공 Windows wheelhouse는 Python 설치 파일을 포함하지 않습니다.

## 시작·정지·재시작·상태·내보내기

아래 명령은 활성화한 가상환경 또는 `.venv\Scripts\gui-test.exe`로 실행합니다. 모든 명령에 같은 `--runtime`, `--port`를 사용하세요.

```powershell
gui-test status --runtime "$env:LOCALAPPDATA\GuiTest" --port 8767
gui-test stop --runtime "$env:LOCALAPPDATA\GuiTest" --port 8767
gui-test restart --runtime "$env:LOCALAPPDATA\GuiTest" --port 8767
gui-test export --runtime "$env:LOCALAPPDATA\GuiTest" --run-id RUN_ID --format pdf --output report.pdf
```

`start`는 분리된 백그라운드 프로세스를 시작합니다. `serve`는 진단용 전경 실행입니다. `standalone/start.ps1`은 설치된 Python을 받아 시작 후 브라우저를 엽니다. PowerShell 실행 정책을 임의 변경하지 않고 위 직접 명령을 사용할 수 있습니다. 서비스 재시작은 진행 중인 TC를 정상 수집한 뒤 수행하세요. 강제 종료 후에는 프로세스 조회 결과에 따라 PAUSED 또는 UNKNOWN으로 복구하며 자동으로 TC를 다시 실행하지 않습니다.

데이터: `%LOCALAPPDATA%\GuiTest\gui-test-standalone-demo\runs.db`, 로그: `%LOCALAPPDATA%\GuiTest\service.log`. 로그/설정/DB를 공개 저장소로 복사하지 않습니다. SQLite DB는 서비스 정지 후 폴더 전체 백업 또는 `Store.backup()`으로 일관된 백업을 만듭니다. 업그레이드는 정지→백업→wheel 설치→시작 순서입니다. DB 스키마는 1이고 예상하지 않은 버전은 거부합니다. 기존 Dashboard DB 스키마는 변경하지 않습니다.

## 사용 흐름과 데모

1. **소스 설정**을 펼쳐 브랜치를 선택한 뒤 **TC 갱신**. 검색/Single·Dual 필터와 폴더 접기는 TC 선택을 유지합니다. 폴더 체크박스는 전체/부분 선택을 표시합니다.
2. Suite 또는 직접 TC 선택 후 **실행 순서의 행을 끌어 위아래로 이동**합니다. 순서 번호 선택으로도 옮길 수 있습니다. 순서를 바꾸면 Preflight를 다시 확인해야 하며, 선행 순서 위반·누락/중복 TC는 서버에서 차단합니다. 기존 Run의 고정 순서는 바뀌지 않습니다.
3. Board A/B 및 COM 선택, 연결 프로파일 저장. 수동 입력은 식별·COM 검증을 우회하지 않습니다. 예시 보드는 `demo-board-a/COM3`, `demo-board-b/COM4`, 호스트 `demo-windows`입니다.
4. Dashboard 모드는 필요하면 **격리 데모 Job 준비**. 미선택 시 일반 Run이며 자동 반영하지 않습니다.
5. 데모 시나리오/속도 선택 → **Preflight 검사 → 테스트 시작**.
6. 환경 오류 시 **데모 연결 / 종료 확인 → 재개**. 복구 확인만으로 자동 재개하지 않습니다. 앞선 결과와 오류 Attempt는 유지됩니다.
7. **결과 리포트**에서 전체 판정과 동기화 상태를 구분하고 내보냅니다. 모든 출력은 MOCK/SIMULATION 근거입니다.

시나리오: 전체 PASS, 2번째 FAIL 후 계속, COM 끊김, Timeout, UNKNOWN, 동기화 일시 장애, 응답 유실 뒤 중복 전송. 실행 중 다음 TC 오류 주입/Job 기준 변경, 정지·취소·제어권 이전, 두 Run의 예약 충돌을 확인할 수 있습니다. Demo에서 복구 확인은 Mock 프로세스가 종료됐다는 어댑터 조회를 수행하며 실제 프로세스 종료로 간주하지 않습니다.

**설정 접기:** 소스 설정, Suite 관리, 연결 및 실행 준비, 실행 순서와 데모 시나리오는 제목을 클릭하거나 Enter/Space로 접고 펼칠 수 있습니다. 접을 때 입력·선택은 유지되며 보드/COM·선택 TC 수 등의 요약을 볼 수 있습니다. 접힘 상태는 브라우저에 기억됩니다. 최초에는 소스 설정만 접히며, 실행·결과는 항상 표시됩니다.

Headless 데모(모든 단계는 같은 Core/Worker/DB 경로 사용):

```bash
python -m gui_test.demo.e2e                  # 단독 5 시나리오
python -m gui_test.demo.e2e --dashboard      # 저장소에서 통합 7 시나리오
```

Demo 브랜치 `demo/main`, `demo/next`는 가상 소스 기준입니다. Core의 `discover(root, metadata, revision)`는 실제 로컬 Git 커밋도 읽지만 UI의 실제 저장소/브랜치 연결은 회사 TC Adapter에 연결할 접점입니다. Run 소스·메타데이터·순서·COM snapshot은 시작 때 고정합니다. 기존 PASS를 새 Run으로 자동 계승하지 않고 보수적으로 전부 재실행합니다.

## 기존 Dashboard에 통합

기준: 공개 `main` **14bb35ea66a328a9de204fbb039cc5d303778b52**. 회사판이 다르면 patch를 그대로 덮어쓰지 말고 각 변경점을 비교합니다.

1. 회사 Dashboard 폴더와 DB를 백업합니다.
2. ZIP의 `gui_test/`를 프로젝트 루트에 복사합니다. `backend/` 전체를 덮어쓰지 않습니다.
3. `git apply --check dashboard-integration.patch` 후 적용하거나 아래 접점만 회사판에 반영합니다.
4. 기존 Dashboard Python 환경에 `gui_test/requirements.lock` 의존성을 검토·설치합니다. 기존 잠금 버전과 충돌하면 해당 환경에서 재검증합니다.
5. React 의존성 설치 및 `npm run build`. 기존 API/Worker를 재시작합니다.

| 접점 | 변경 |
|---|---|
| `backend/api/main.py` | `/api/v1/gui-test` Router와 오류 핸들러 추가. 기존 안전 미들웨어를 그대로 통과 |
| `backend/worker/main.py` | 기존 단일 Worker 프로세스 안 GUI Worker tick/recover, 실제 실행은 HTTP 요청과 분리 |
| `backend/domain/engine.py` | 내부 `automatic_device_test(run)`, 완료 Job의 재검증 승인 동작. 기존 manual-test 보존 |
| `apps/web/src/main.tsx` | 좌측 `Test 현황` 메뉴와 공통 `gui_test/web/TestPage.tsx` |
| `apps/web/vite.config.ts`, `tsconfig.json` | 외부 공통 컴포넌트의 React 단일 인스턴스·타입 해석, 단독 UI 빌드 모드 |
| `pyproject.toml` | GUI Test 자동 시험 검색 경로 추가 |

Dashboard 실행 방법은 기존 [README](../README.md)를 따릅니다. 예:

```bash
python scripts/serve.py --runtime .runtime --port 8765
# 별도 터미널
python -m backend.worker.main --runtime .runtime
```

Mock 통합 DB는 `.runtime/gui-test-dashboard-demo/runs.db`와 `demo-dashboard.db`입니다. 기존 `.runtime/dashboard.db`와 분리됩니다. 데모 Job 생성은 사용자가 버튼을 눌렀을 때만 수행합니다. 현재 자동 결과 접수는 **서버 내부 메서드**이며, 클라이언트가 PASS JSON을 제출하는 공개 API가 아닙니다.

## 실제 회사 TC/RBM 연결 계약

이미 기존 명령이 COM 인자를 지원한다는 사실은 확정입니다. **정확한 플래그·인자 순서·실행 호스트만 미정**입니다. 새 사내 API나 명령 문법을 만들어 가정하지 않았습니다.

- `adapters/runner.py`: `Runner.execute(tc, connections, timeout, context, emit, cancelled)`와 `probe(process_ref)`를 구현합니다. `resolve_argv()`는 등록된 배열의 독립 `{tc_path}`, `{com_a}`, Dual의 `{com_b}` 슬롯을 치환합니다. 옵션/위치는 실제 성공한 Single/Dual 명령에 맞추고 `shell=False`로 전달합니다. UI에서 임의 명령/추가 Python 인자를 받지 않습니다.
- 허용된 TC 루트/스크립트·원격 실행 주체·인증은 서버 측 등록만 허용합니다. SSH 키/토큰은 OS 자격증명 저장소/환경에서 읽고 argv/보고서에 포함하지 않습니다. 종료 확인·프로세스 재조회·출력 제한을 구현하기 전에는 운영 Runner를 활성화하지 않습니다.
- `adapters/rbm.py`: 보드 ID/호스트/COM의 **조회·검증** 계약입니다. 등록은 기존 RBC 책임입니다. RBM에 TC 실행/점유 기능이 있다고 가정하지 않습니다. 수동 입력도 같은 검증을 거칩니다.
- 보드 COM 변경은 신뢰성 있는 동일 보드 확인 후 사용자에게 제안해야 합니다. 자동 재배정은 하지 않습니다. 현재 데모는 기존 매핑과 다르면 차단합니다.
- `adapters/dashboard.py`: 현재 Job/이미지/Plan/fingerprint/Attempt/필수 사례를 고정하고 종료 후 재검증합니다. 실제 이미지 attestation과 회사판 Delta가 없으므로 운영 결과 쓰기는 명시적으로 거부합니다. 파일 SHA와 장치 버전 문자열이 같다고 가정하지 않습니다.
- 필수 운영 값은 [production.example.json](config/production.example.json)의 `null` 자리를 승인된 값으로 채웁니다. 이 파일은 체크리스트이며 런타임에서 읽어 하드웨어를 켜는 스위치가 아닙니다. timeout/로그 보존·용량/재시도 수를 임의 데모 기본값으로 운영하지 않습니다.
- TC 메타데이터 및 모듈 매핑 예시는 [config](config/)에 있습니다. 사내 원본을 공개 Git에 추가하지 마세요.

현재 데모 제한은 TC timeout 10초, Attempt 스트림당 64 KiB, 제어권 heartbeat 만료 60초, 동기화 자동 재시도 2회입니다. 운영값이 아닙니다. 원본 로그와 판정·감사 이력은 자동 삭제하지 않습니다. 전체 로그 ZIP을 압축 보관할 수 있으며, 회사 보존 정책에 따른 자동 정리/증빙 보호 정책은 실제 저장소 Adapter와 함께 적용해야 합니다. 단일 사용자 loopback/SSH 모델이며 제어권 세션은 사용자 인증이 아닙니다.

완료 Job 자동 결과는 새 Attempt로 이력을 남기고 최종 사람 검토를 무효화합니다. 기존 boot→main 게이트와 integration 의존성을 사용합니다. boot FAIL에 영향을 받는 main 장비 시험을 무효화하고 독립 모듈 결과는 보존합니다. `gui_revalidation`의 대상/순서를 확인 후 `approve-gui-revalidation` 명령으로 승인해야 재배정할 수 있습니다. 회사판의 추가 DAG가 불명확하면 운영 연결을 보류해야 합니다.

## 개발·검증·패키징

```bash
python -m venv .venv
# Windows: .venv\Scripts\python.exe, Linux: .venv/bin/python
python -m pip install -r gui_test/requirements.lock
cd apps/web
npm ci
npm run build
npm run build:gui-test
npx playwright install chromium
cd ../..
python -m pytest -q
python scripts/test_e2e.py
python gui_test/demo/browser_e2e.py
python -m gui_test.demo.e2e --dashboard
python -m pip wheel ./gui_test --no-deps --no-build-isolation -w .local-reports/wheels
python -m pip download -r gui_test/requirements.lock --dest .local-reports/wheelhouse-win-py312 --platform win_amd64 --python-version 312 --implementation cp --abi cp312 --only-binary=:all:
python gui_test/standalone/package.py --base 14bb35ea66a328a9de204fbb039cc5d303778b52 --wheelhouse .local-reports/wheelhouse-win-py312 --wheels .local-reports/wheels
```

GitHub Actions는 Linux 전체 회귀/브라우저와 Windows 모듈 시험/설치 후 시작·상태·정지 smoke를 실행합니다. Node.js는 빌드 PC에서만 필요합니다. Python 주요 의존성: FastAPI 0.143.0 / Uvicorn 0.54.0 / Pydantic 2.14.0 / ReportLab 4.4.3 / pyserial 3.5. 전이 의존성은 `requirements.lock`, 웹 의존성은 `apps/web/package-lock.json`에 고정합니다.

브라우저 테스트는 새 임시 runtime을 생성하며 운영 DB를 재사용하지 않습니다. `BSP_BROWSER_EXECUTABLE`로 승인된 로컬 Chromium 경로를 지정할 수 있습니다. 실제 Windows COM 연결·SSH/Linux TC·회사 RBM·회사판 Dashboard는 별도 현장 인수가 필요합니다. 검증 범위와 최초 실패/수정 기록은 [검증 기록](VALIDATION.md)에 남깁니다.
