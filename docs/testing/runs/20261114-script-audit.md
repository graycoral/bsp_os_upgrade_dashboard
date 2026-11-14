# 2026-11-14 전 프로젝트 스크립트 정리 조사

기준: `e4f53ca1ec288feb3eb1b9ccff8335a398ad321c`, main. 기존 설계 문서 WIP를 보존한 읽기 전용 조사다. 이 기록 작성 시 제품 스크립트 변경·실행·새 EXE 생성·게시·실제 보드/모델 호출은 없다. 조사 범위는 Git 추적 스크립트·앱 명령·CI·패키징·호출 시험이며 `.venv`, `node_modules`, runtime, 생성 산출물은 제외했다.

## 역할별 목록과 판단

| 현재 파일/명령 | 실제 역할 | 정리 판단 |
|---|---|---|
| 루트 `board-connector.cmd` → `scripts/board_connector.py` | Windows Python 3.13 우선 탐색, 조건부 환경 준비, Qt GUI 실행 | 사용자 진입점 유지. Z:/UNC·공백 경로·다른 CWD 계약을 보존한다. |
| 루트 `run.sh` → `scripts/start.sh` | 이미 준비된 `.venv`와 UI로 개발용 Agent Monitor API/Worker 실행 | 루트 담당자가 만드는 공통 lifecycle manager 호출 하나로 `run.sh`를 정리하고 `scripts/start.sh` 제거 예정. 별도 영속 실행 구현을 중복 작성하지 않는다. |
| `scripts/setup.{sh,cmd,ps1}` → `setup_runtime.py` | Linux/Windows 설정 메뉴와 `run`, `doctor`, `ports` | 운영 CLI는 하나의 구현이다. OS별 인자 전달 진입점은 중복 구현이 아니므로 유지 권장. PS1은 명시 PythonExecutable 지원이 있다. |
| `scripts/run.{sh,cmd}`, `doctor.{sh,cmd}` | `setup.* run/doctor` 단순 별칭 | 4개 제거 가능. 현재 안내·PORT-006과 legacy EXE source allowlist·opt-in smoke의 파일 목록을 함께 갱신한다. |
| `scripts/build.{sh,cmd,ps1}` | Dashboard/GUI Test UI 빌드 | `build-ui.*`로 명명해 ZIP 조립과 구분. CMD는 child 정책·PSModulePath 처리, PS1은 Windows 실행, Bash는 POSIX 실행을 맡으므로 OS 진입점들은 유지한다. |
| `apps/gui-test/build.{cmd,ps1}` | Windows Python 3.12 x64 wheel·오프라인 ZIP·설치 smoke | `build-windows-package.*`로 명명. UI 빌드와 달라 합치지 않는다. Dashboard/Git 없는 독립 반입 계약 보존. |
| `apps/gui-test/start.ps1` → `launch.py start` | GUI Test 웹 서비스 시작 후 브라우저 열기 | `launch.py start`를 정식 명령으로 삼으면 별도 wrapper 제거 가능. 브라우저 자동 열기는 문서에서 명시하며 backend 시작에 섞지 않는다. |
| `apps/gui-test/launch.py` | 소스 layout의 정적 자산 위치를 명시한 standalone CLI | 유지. 설치 wheel의 `gui-test`와 소스 namespace가 달라 단순 중복이 아니다. |
| `apps/gui-test/package.py` | 소스 ZIP, host integration, UI/headless wheel staging | 유지. 플러그인 복사형 전달/bootstrap 구현과 소유권을 맞춘다. |
| `scripts/build-editable-runner.{cmd,ps1}` → `build_editable_runner.py` | 고정 embedded Python·wheel 입력으로 편집형 소스 bundle 조립/repack | legacy EXE builder와 다르다. 유지하되 현 표시명에 맞춘 `build-connector-bundle.*`/`build_connector_bundle.py` 명명은 선택 가능. embedded Python 3.12.10 입력/잠금·검증을 일반 GUI의 Python 3.13과 혼동하지 않는다. |
| `scripts/build_windows_runner.py`, `packaging/windows-runner.spec`, `windows-runner-build.lock` | 과거 PyInstaller EXE 조립 | 새 EXE를 만들지 않는 현재 방향에서 제거 후보. live 코드·시험에서 builder import/call 없음. 3개를 함께 제거하고 현재 안내를 소스 방식으로 바꾼다. |
| `scripts/windows_runner_entry.py` | frozen 호환 실행·contained-child gate·wizard/host dispatch | builder 제거와 별개로 유지. 기존 frozen runtime 경계 시험과 `test_runner_ports.py`가 실제 import한다. |
| `scripts/serve.py` | Agent Monitor API만 실행 | 유지. `serve_monitor.py`로 명명 가능. setup_runtime Linux 실행과 E2E가 호출한다. |
| `scripts/configure.py` | BSP profile import/export/validate | 유지. `manage_profile.py`로 명명 가능. wizard 연결 설정과 데이터가 달라 합치지 않는다. |
| `scripts/setup_ports.py`, `setup_flashing.py` | wizard 내부 공통 설정 구현 | 진입 스크립트가 아닌 import 모듈. 유지. editable bundle allowlist/repack의 계약이다. |
| `scripts/create_flash_manifest.py` | 이미지 파일 해시 manifest 생성 | 유지. 실제 flash 명령과 다름. wizard의 `python -m scripts.create_flash_manifest` 참조 보존. |
| `scripts/claude_orchestrator.py` | 사용자 수동 JSON 검사·패키지 내보내기 | D-40 고정 경로 계약으로 유지. 실제 LLM 실행이 아니다. |
| `scripts/test_e2e.py` | 새 runtime/API/Worker와 Dashboard Playwright 시험 | `test_dashboard_browser.py`로 명명 가능. standalone `backend.gui_test.demo.browser_e2e`와 서로 다른 호스트를 검증한다. |
| `apps/web/package.json`의 `build:gui-test` | 형제 앱 npm build 별칭 | 제거 가능. `npm run build --prefix apps/gui-test`로 현재 호출·문서 교체. 각 앱의 자체 npm build/dev/preview는 유지. |
| `apps/gui-test/pyproject.toml` CLI 4개 | 설치형 `gui-test`, `gui-test-runner`, `gui-test-connector`, `gui-test-integration` | 공개 설치 CLI 계약이므로 유지. |
| `docs/testing/validate_docs.py` | 문서 링크·RQ/T·결과 CSV 검증 | 유지. 제품 스크립트와 다름. |
| `workflow_diagram/tests/run.cjs`, Playwright 설정/fixture | workflow 공유 UI 검증 | 유지. Dashboard E2E와 달라 통합하지 않는다. |
| `tests/editable_runner_smoke.py`, `portable_runner_smoke.py` | 각각 편집형 소스 bundle/과거 frozen EXE opt-in 시험 | 서로 다른 배포 형식. 과거 frozen smoke는 보존하거나 legacy임을 명시한다. 실행하려고 새 EXE를 만들지 않는다. |
| `docs/diagram-design-20261103/{build_diagrams,verify_diagrams}.py` | 고정 revision 다이어그램 재현·기하 검증 | 과거 산출물 재현용으로 보존. verify는 과거 Windows plugin 절대경로 의존이며 현재 실행 가능으로 주장하지 않는다. |

동일 파일 바이트의 중복을 제거하는 작업보다는 단순 별칭 제거와 역할을 드러내는 명명이 핵심이다. OS별 wrapper나 소스/설치 namespace, UI/ZIP/embedded bundle 역할을 하나로 합치면 독립 반입 또는 실행 계약이 깨진다.

## 원자적으로 갱신할 호출·문서

- `run.sh`/`start.sh`: 루트 README, scripts 안내, Windows Runner 안내, 현재 플러그인 설계의 개발 실행 경로. 새 service bootstrap과 이중 Worker를 만들지 않는다.
- UI 빌드 명명: `.github/workflows/gui-test.yml`, `tests/test_build_entrypoint.py`, 루트/스크립트 안내, 현재 PORT/UI 빌드 안내. Windows CMD의 LF/CRLF·Restricted 상속·인자·종료 코드·PSModulePath 회귀를 보존한다.
- Windows 패키지 명명: `.github/workflows/gui-test-windows-build.yml`, `apps/gui-test/package.py:APP_FILES`, `backend/gui_test/tests/test_package.py`, `tests/test_gui_test_layout.py`, GUI layout 계약·WINDOWS_BUILD·구현 계획. 독립 소스 ZIP에 새 파일명까지 포함되어야 한다.
- alias 제거: `RUN_AND_DIAGNOSE.md`, `SETUP_COMMANDS.md`, `PORT-006.md`, scripts 안내. 기존 배포본 내부 `launch-run.cmd`/`diagnose.cmd`와 소스 wrapper를 구분한다. 이미 배포된 artifact의 내용이나 과거 실행 기록을 다시 쓰지 않는다.
- legacy EXE builder 제거: `PORT-003.md`, `PORT-006.md`, `WINDOWS_RUNNER_PORTABLE.md`, 현재 플러그인 설계, editable 설계의 링크. 과거 버전 고정 이력은 보존하고 제거 시점/대체 경로를 덧붙인다. 문서 링크 검증기는 과거 문서의 사라진 파일 링크도 확인하므로 plain code 경로 또는 보존된 계약 문서 링크로 바꾼다.
- Python 실행기 명명 선택 시 모든 문자열 호출, imports, 패키징 allowlist/provenance hash, fixture 생성 파일명을 함께 갱신한다. 특히 editable builder 자체 명명은 생성 `repack.cmd`의 `python -m scripts.build_editable_runner`와 동봉 `SCRIPT_NAMES`를 함께 바꿔야 한다.
- 모든 current 안내의 sibling build 별칭을 제거하되 고정 커밋의 실제 PASS 명령이 적힌 과거 `runs/`, WORK_STATUS, REGRESSION_LEDGER, TEST_RESULTS의 증거는 보존한다. 현재 명령으로 오인되지 않도록 migration 안내를 연결한다.

## 권장 구현 순서와 검증

1. 독립 요구사항 리뷰 후 부모 에이전트가 bootstrap/export와 스크립트 소유 파일을 확정한다. 이 조사 자체는 구현 승인을 추가로 요구하지 않는다.
2. 현재 사용자 진입점·설정·runtime·DB를 보존하며 단순 별칭 제거, 명명, 호출/패키징 갱신을 한 단위로 반영한다. DB 이전·외부 서비스 설정 변경 없음.
3. `git diff --check`, 남은 old-path 문자열/동적 module 참조 조사, Bash 구문·Python import/CLI help를 확인한다. 삭제된 경로는 과거 증거/명시 migration 문맥에서만 허용한다.
4. 관련 `test_build_entrypoint`, `test_setup_commands`, `test_setup_runtime`, `test_runner_ports`, `test_windows_runner_bundle`, `test_editable_runner_build/runtime`, `test_gui_test_layout`, GUI package/portability 시험을 수행한다. fixture만 이름을 바꿔 요구사항 검사를 약화하지 않는다.
5. 양 UI build, 원본 저장소 없는 source export/wheel staging·zip 명세·installed CLI/정적 자산 smoke, 필요 시 Dashboard/standalone 브라우저 회귀를 수행한다. 새 EXE를 만들지 않는다.
6. 로그는 `.local-reports/<고유 run-id>/` 아래에 전체 출력·실제 종료 코드와 함께 보존한다. 기존 실패 이력을 남기고 이번 실행의 PASS/FAIL/SKIP/NOT_RUN을 구분한다. 로컬 Mac은 실제 Windows CMD/Python3.13/Z:/UNC·PowerShell 빌드나 Linux service acceptance를 대신하지 않는다.

이 조사 시점 제품시험: **NOT_RUN**. 정적 읽기/호출 검색만 수행했다. 실제 Windows Z:/UNC·Python3.13, 회사 TC·보드·SSH·LLM 인수는 **NOT_RUN**이다.
