# GUI Test 소스·앱·공유 UI 경계

RQ-54 / D-57, 2026-11-05 사용자 승인 구조 변경이다. API·저장 형식·설정·실행 정책을 바꾸지 않고 독립 앱과 재사용 기능의 위치를 분리한다. 구현·시험·검토 상태는 [실행 기록](../testing/runs/20261105-gui-test-layout.md)을 따른다.

## 소스 구조와 의존 방향

| 위치 | 책임 |
|---|---|
| `apps/gui-test/` | 단독 앱의 launch.py, 빌드·패키징 진입점, 전용 웹 빌드 설정, 정적 자산·설정 예제·의존성 잠금 |
| `backend/gui_test/` | 공통 Python core/API/adapter/execution, 단독 서비스 구현, Mock/demo·Python 시험 |
| `packages/gui-test-ui/src/` | Dashboard와 단독 앱이 재사용하는 React 화면·컴포넌트·스타일 |
| `apps/web/` | Dashboard 호스트. 공통 UI를 import하고 기존 API를 사용 |

소스 Python import는 `backend.gui_test.*`다. 루트 `gui_test/`나 호환 import shim은 두지 않는다. backend 소스가 `apps/`를 import하거나 그 경로를 찾아 설정·정적 파일을 읽지 않는다. 단독 앱의 `launch.py`가 앱 정적 자산 위치를 서비스에 전달한다. 공통 UI는 두 호스트의 앱 구현을 역참조하지 않는다. 별도 사본으로 UI를 복제하지 않는다.

소스 실행은 저장소 또는 독립 소스 묶음의 루트에서 다음과 같이 한다.

```sh
python -m pip install -r apps/gui-test/requirements.lock
npm ci --prefix apps/gui-test
npm run build --prefix apps/gui-test
python apps/gui-test/launch.py start --runtime .runtime-gui-test --port 8767
python apps/gui-test/launch.py status --runtime .runtime-gui-test --port 8767
python apps/gui-test/launch.py stop --runtime .runtime-gui-test --port 8767
```

`serve`, `restart`, `export`도 같은 소스 진입점을 사용한다. 실행기의 소스 모듈 호출은 `python -m backend.gui_test.execution.host`다. 설치된 CLI와 혼동하지 않는다.

## 독립 소스 반입

예전 `gui_test/` 한 폴더 복사 계약은 세 경로의 상대 구조를 유지하는 소스 내보내기로 대체한다. `apps/gui-test/`만 복사해서 빌드하는 계약이 아니다.

```text
<source-root>/
  apps/gui-test/
  backend/__init__.py
  backend/gui_test/
  packages/gui-test-ui/src/
```

`python apps/gui-test/package.py --standalone`이 이 구조의 ZIP을 만든다. `backend/__init__.py`는 내보낸 묶음에 필요한 최소 파일이며 Dashboard backend 전체를 복사하지 않는다. `apps/web`, Git 이력, 루트 Dashboard 의존성·DB·runtime·자격증명은 독립 빌드에 필요하지 않다. Python/npm 의존성은 잠금 파일과 승인된 저장소 또는 오프라인 wheelhouse로 별도 준비한다. 전체 backend가 없는 경로에서 빌드·Mock 서비스·패키지 경계를 시험한다.

## 빌드와 설치 패키지

Windows 정식 단독 빌드 진입점은 `apps/gui-test/build.ps1`이며 `build.cmd`는 같은 앱의 래퍼다. 정적 결과는 `apps/gui-test/static/`에 생성한다. Dashboard의 `npm run build:gui-test --prefix apps/web`는 형제 앱 빌드로 위임하는 편의 명령이다. 독립 빌드가 이 명령이나 `apps/web`의 도구를 필요로 해서는 안 된다.

여러 소스 경로를 setuptools가 직접 탐색하게 하지 않고 wheel용 임시 트리를 먼저 만든다.

```sh
python apps/gui-test/package.py --stage-wheel <stage-dir>
python -m pip wheel --no-deps --no-build-isolation --wheel-dir <wheel-dir> <stage-dir>
```

staging은 공통 Python 구현을 설치 패키지 `gui_test/`로 배치하고 앱의 정적 파일·설정과 패키지 메타데이터를 합친다. 설치 후 import 이름 `gui_test.*`, 배포 이름 `bsp-gui-test`, `gui-test`와 `gui-test-runner` CLI는 유지한다. 설치된 wheel은 저장소의 `backend`, `apps`, `packages` 경로 없이 실행되어야 한다. 직접 `pip wheel backend/gui_test` 또는 `pip wheel apps/gui-test`를 실행하는 방식을 안내하지 않는다.

## 데이터와 운영 경계

이 변경은 파일 배치와 빌드 입력 변경이다. `/api/v1/gui-test`와 live 경로, SQLite schema/runtime 위치·설정 키·토큰·브라우저 저장 선호·기존 Run/Suite/Attempt는 유지한다. 백업 없는 삭제나 데이터 재생성을 수행하지 않는다. 통합 모듈 선택 서비스의 주입과 단독 앱의 운영 컨텍스트 거부도 보존한다. 상세 필드와 판정 규칙은 [GUI Test 계약](GUI_TEST_CONTRACT.md), 모듈 선택은 [관련 계약](MODULE_TC_SELECTION.md)만 기준으로 사용한다.

실제 보드·모델·Jira·회사 환경 인수는 이번 구조 변경 검증에 포함하지 않는다. 이전 고정 커밋·시험 로그에 적힌 `gui_test/` 경로는 당시 증거이며 새 경로로 고쳐 쓰지 않는다. 기존 운영 정상 기준은 유지한다.

## 검증 기준

T-164는 소스 의존 방향·옛 루트 제거·변경 전 파일 보존, T-165는 두 UI의 공통 소스 사용과 빌드, T-166은 세 경로 독립 반입·Windows 빌드·CLI, T-167은 wheel staging·설치 네임스페이스·정적 자산, T-168은 기존 runtime·API·실행 계약과 Mock 회귀를 검사한다. 실행 결과와 독립 검토 결과는 각각 증거 확보 뒤 기록한다.

## 회사 호스트 경계 · RQ-57/D-61

공통 Python은 `backend.domain`, `backend.services`, 호스트 API/worker를 역참조하지 않는다. Dashboard 결과·모듈 선택·데모 job 접점은 호스트 `backend/services/gui_test_host.py`에 두고 공통 `make_manager`에 adapter를 주입한다. `make_dashboard_manager(runtime, *, engine=None, module_selection_service=None)`가 호스트 조립을 맡고, `demo_router(manager, live=False)`는 공통 router와 분리해 기존 `/api/v1/gui-test` prefix에 mount한다. `automatic_result`는 내부 신뢰 수신이며 공개 PASS 등록 API가 아니다. API·worker·domain·실제 장비 정책은 보존한다.

`package.py --base`는 누적 patch의 불완전한 의존성 수집 때문에 폐기하며 프로그램 호출도 파일 수집과 출력 경로 접근 전에 거부한다. `--host-integration --target bsp-dashboard-host-v1`은 GUI 세 경로의 현재 소스와 명시적 계약·검토용 host-reference만 내보낸다. built static·wheel은 제외하고 UI를 빌드해야 한다. `--standalone` 및 `--stage-wheel`은 기존 Git 독립 빌드 계약을 유지한다. 미지원 target·충돌 옵션은 조기 거부한다.

호스트 ZIP은 HEAD/dirty·파일 SHA256·세 roots·reference 대응·필수 호스트 계약·잠금 파일·시험 명령·실제 검증 범위를 `HOST_INTEGRATION.json`에 기록한다. `SHA256SUMS.json`은 자신을 제외한 모든 entry를 포함한다. 생성된 INSTALL/RELEASE_SUMMARY/계약 문서는 ZIP 내부에서 독립적으로 읽고, 과거 문서 그래프를 무제한 복사하지 않는다. 회사 backend 전체나 workflow/overview 변경을 누적 반입하지 않는다. UI의 공개 entrypoint·스타일과 회사 동일성 절차는 [UI 이식 계약](UI_PORTABILITY.md), 현재 미커밋 전달은 [PORT-004](../porting/PORT-004.md), 실행 상태는 [기록](../testing/runs/20261106-portability.md)을 따른다.
