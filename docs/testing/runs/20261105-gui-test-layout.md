# GUI Test 구조 분리 · 2026-11-05

상태: **LOCAL_VERIFIED — 2026-11-06 현재 소스 회귀·두 UI 빌드·독립 패키지 인수 PASS, 최종 독립 Astra 코드 리뷰 APPROVED**. RQ-54/D-57, T-164~168 로컬 검증 완료. 실제 장비·모델·Jira·SSH·회사 환경은 실행하지 않는다. 이 로컬 결과를 운영 인수나 배포 완료로 표시하지 않는다. branch push·PR/CI·main 병합 상태는 조정자가 실제 수행 후 별도 기록한다.

## 범위와 기준

루트 `gui_test/`를 `apps/gui-test/`, `backend/gui_test/`, `packages/gui-test-ui/src/`로 나눈다. 소스 import는 `backend.gui_test.*`, 설치 wheel import는 기존 `gui_test.*`와 `gui-test`/`gui-test-runner` CLI를 유지한다. API·DB·runtime·설정과 실행 정책은 유지한다. [구조 계약](../../design/GUI_TEST_LAYOUT.md), [Windows 빌드](../../gui_test/WINDOWS_BUILD.md)를 따른다.

작업 시작 시 RQ-52 Git 정보/RQ-53 모듈 TC 선택/D-54 화면 정리의 기존 미커밋 변경이 있었다. 이들을 보존하며 구조만 이관한다. 고정 Git commit만으로 당시 작업 트리를 표현하지 않는다. 이동 전 파일 목록·해시는 `.local-reports/20261105-gui-test-layout/before-move-manifest.json`, 복사본은 같은 경로의 `before-move/`에 있다. 이 경로들은 로컬 전용이며 저장소에 포함하지 않는다.

## 역할 배정

| 단계 | 실제 배정 / 현재 상태 |
|---|---|
| 요구사항 분석 | GPT-6 Astra XHigh, 완료된 분석을 구현 입력으로 전달 |
| 아키텍처 설계 | GPT-6 Astra XHigh, 완료된 구조 설계를 구현 입력으로 전달 |
| 상세 설계 | GPT-6 Astra High, 완료된 소스·설치 경계 설계를 구현 입력으로 전달 |
| 구현·문서 | GPT-6.1 Sol High, 소스 구현과 문서를 파일 소유권으로 분리해 진행 |
| 시험 작성 | GPT-6.1 Sol Medium, 별도 담당자가 구조·패키지 경계 시험 작성 |
| 시험 실행·보고 | 새 GPT-6 Luna Low, 현재 트리의 회귀·UI·live-view 실행과 별도 패키지 인수 담당 |
| 최종 독립 코드 리뷰 | 사용자 override로 새 GPT-6 Astra High, 2026-11-06 최종 재검토 APPROVED; 시험은 실행하지 않음 |

검토는 저장소 코드의 독립 검토이며 실제 Claude/BSP 호출이 아니다. 리뷰의 APPROVED와 별도 실행의 PASS를 구분한다. 초기에 기록한 NOT_RUN/NOT_REVIEWED는 당시 상태이며 아래 실제 근거로 갱신한다.

## 인수 상태

| ID | 범위 | 현재 상태 |
|---|---|---|
| T-164 | 이동 전 manifest와 비교; 미커밋 파일 보존; 루트 shim 없음; Python/UI 의존 방향 | PASS — 독립 소스 대조·구조 시험; Windows symlink 사례는 SKIP 별도 |
| T-165 | Dashboard 및 단독 UI TypeScript/production 빌드; 공통 화면 import와 관련 브라우저 회귀 | PASS — 두 production 빌드·합성66·단독18·live 1+1 |
| T-166 | 독립 세 경로 ZIP; Dashboard/Git 없는 공백 경로의 Windows 빌드; 소스 서비스/CLI smoke | PASS — 실제 무Git PATH의 기본 builder134 PASS·4 deselected; source health/JS/CSS HTTP200 |
| T-167 | staging wheel 생성·격리 설치; gui_test import와 CLI; 정적 파일/config 패키지 경계 | PASS — 격리 wheel 설치·GUI CLI lifecycle·Mock demo5; 새 Runner 실제 pytest7 PASS |
| T-168 | Python/Mock/API/runtime 복구 및 RQ-52/53/D-54 관련 회귀; 문서 정합성 | PASS — 회귀384/6 SKIP·문서 검사 exit 0 |

패키지 인수는 `python apps/gui-test/package.py --standalone`, `python apps/gui-test/package.py --stage-wheel <stage-dir>`, 설치 wheel과 소스의 서비스 생명주기, Windows 독립 빌드를 별도 실행했다. 처음 NOT_RUN으로 둔 T-166/167은 아래 실제 독립 실행 결과 수신 후 PASS로 갱신했다.

## 2026-11-06 현재 소스의 독립 실행 근거

기준 branch는 `refactor/gui-test-layout`, 당시 HEAD는 `197be637cd7d9bd0430751b177f601f5d54789cf`다. 미커밋·미추적 구현을 포함하므로 HEAD만으로 현재 소스를 표현하지 않는다. 최종 Astra의 109개 파일 SHA256은 `.local-reports/20261105-gui-test-layout/astra-review-manifest.json`에 있으며 이 파일 자체의 SHA256은 `811ba47e9549cb1e76a2a761ac99b05e70ff8f6841b09a9ff61cf65727543fe5`다. 구조 시험 `tests/test_gui_test_layout.py`의 SHA256은 `98d292551d9226d30398ea098476532d75b77a18f9210e4ee5ee65f89b8a7cbd`다. 이후 완료 근거만 갱신한 문서와 제품 소스 변경을 구분한다.

조정자의 최종 소스 대조 `precommit-reviewed-source-audit.json`은 리뷰 대상 109개 전부 현재 파일과 일치해 `mismatches=[]`임을 확인했다. 완료 기록·CSV의 문서 갱신은 이 제품 소스 승인의 범위를 바꾸지 않는다.

리뷰·패키지에 포함한 `apps/gui-test/VALIDATION.md`의 2026-11-05 NOT_RUN/NOT_REVIEWED 문장은 초기 작성 시점의 기록이다. 승인·시험한 109개 파일과 artifact의 동일성을 유지하기 위해 그 바이트를 보존하며, 현재 판정은 이 실행 기록·최신 CSV·WORK_STATUS를 따른다. 앱 README도 최종 승인 해시를 그대로 유지한다.

환경: Windows x64, Python 3.13.5, Node 24.21.0/npm 11.19.0, Vite 7.3.7, Playwright 1.64.0, Chrome 156.0.8078.80. Windows 배포용 고정 Python/Node의 패키지 인수와 이 개발 회귀 환경은 별도다. 아래 로그는 모두 `.local-reports/20261105-gui-test-layout/final-20261106-exec/` 아래 로컬 전용 파일이며 Git에 포함하지 않는다. 실행 담당의 요약은 `execution-summary.json`이며 snapshot은 `2026-11-06T00:16:10+09:00`이다.

| 실행 | 결과 | 근거 파일 |
|---|---|---|
| `tests/test_gui_test_layout.py`, `backend/gui_test/tests`, `tests/test_setup_runtime.py`, `tests/test_build_entrypoint.py`, `tests/test_windows_runner_bundle.py`, `tests/test_hardware_pipeline.py`의 focused pytest | exit 0, **384 PASS / 6 SKIP / 2 warnings**; 짧은 `--basetemp .local-reports/t6a` 사용 | `python-regression-short.log`, `.xml`, `.exitcode` |
| `npm.cmd run build --prefix apps/web` | exit 0, production PASS, 1600 modules | `build-web.log`, `.exitcode` |
| `npm.cmd run build --prefix apps/gui-test` | exit 0, production PASS, 37 modules | `build-gui-test.log`, `.exitcode` |
| workflow 합성 브라우저 회귀 | exit 0, **66 PASS**, delayed settings save 포함 | `workflow-browser.log`, `.exitcode` |
| 단독 GUI Mock 브라우저 | exit 0, **18 PASS**, 좌우 정렬·설정·실행 화면 포함 | `standalone-gui-browser.log`, `standalone-gui-browser-playwright.log`, `.exitcode` |
| 통합 live-view | exit 0, **1 PASS**, 격리 API와 소유한 로컬 harness | `integrated-live-browser.log`, `.exitcode`, `run-live-view.py` |
| 단독 live-view | exit 0, **1 PASS**, 격리 launch serve와 소유한 로컬 harness | `standalone-live-browser.log`, `.exitcode`, `run-live-view.py` |

6 SKIP은 Windows 권한으로 symlink를 만들지 못한 3개와 Linux POSIX 권한·session 정리·Bash 전용 3개다. 이를 PASS로 세지 않으며 Linux 실행 근거로 사용하지 않는다. 경고 2개는 기존 Starlette/httpx 사용 중단 예고와 pytest cache 쓰기 권한 경고다.

초기 같은 회귀 실행은 긴 임시 경로와 PowerShell 실행 정책 영향으로 exit 1, **367 PASS / 5 FAIL / 12 ERROR / 6 SKIP**이었다. `python-regression.log`·`.xml`·`.exitcode`를 보존한다. 경로를 짧게 하고 해당 자식/프로세스 범위의 `PSExecutionPolicyPreference=Bypass`만 적용해 같은 시험을 다시 실행했으며 이후 원래 값을 복원했다. 시스템·사용자 저장 정책이나 제품 시험 조건을 완화하지 않았다. 앞선 재사용 세션의 sandbox 접근 실패는 당시 세션의 제한이며 Python이 실제 설치되지 않았다는 근거가 아니다. 재개 전 production 두 빌드의 PASS도 당시 이력으로 보존하되 최종 판단에는 위 현재 실행을 사용한다.

RQ-20/39/52/53의 승인된 변경도 현재 작업 트리에 함께 보존해 검증했다. [원래 기능 실행 기록](20261104-test-results-cleanup.md)의 초기 FAIL·검증 사본·차단 이력은 유지하며 현재 트리의 회귀 결과를 후속 근거로 연결한다. 실제 사용 중인 서비스의 배포·재시작은 수행하지 않았다.

## 최종 독립 코드 리뷰와 수정

새 Astra High의 최종 보고 `.local-reports/20261105-gui-test-layout/astra-review.md`는 **APPROVED**, 미해결 material finding 없음이다. 구현·시험·문서를 수정하지 않은 독립 소스 검토이며 시험 PASS를 주장하지 않는다. 이동 전 보존본과 canonical Python, 공통 UI와 앱 소비자, source/installed CLI, ZIP/wheel allowlist, Windows builder·CI, frozen Runner를 대조했다. 병행 RQ-20/39/52/53의 별도 기능 리뷰를 대신하지 않는다.

- REG-0048: 단독 builder가 Git가 필요한 integration patch 시험까지 선택하던 P2. 단독의 `-k`에서 정확히 해당 시험만 제외했고 전체 저장소 회귀에는 원래 시험을 유지했다. 무Git 독립 builder 인수는 별도 패키지 결과로 확정한다.
- 개발 README가 Dashboard 의존성만 설치한 뒤 형제 앱 빌드를 호출하던 P2. `npm ci --prefix apps/gui-test`를 먼저 실행하도록 보완했다.
- REG-0049: 위 문서 수정 중 한국어 UTF-8이 실제 손상됐다. 정상적인 직전 wheel staging의 README를 그대로 복원하고 ASCII npm 명령 한 줄만 삽입했다. 최종 SHA256은 `99bd53a0e86dd5c623114f9aa5d812cce19f9b648f59459554bcfb29ed567360`이다. Astra가 전체 복원 내용과 의도한 한 줄 차이를 독립 대조했고 `readme-encoding-repair-20261106/verification.json`에 원본·복원 해시와 검사 근거를 보존했다. 손상본·최초 finding은 삭제하지 않았다.

수정 커밋은 이 변경을 처음 포함하는 커밋으로 추적한다. 최종 패키지는 위 README와 source manifest 기준으로 다시 생성해 확인했으며 과거 산출물로 대체하지 않았다. 커밋·main 병합·원격 push는 조정자가 처리하고 실제 완료 뒤 기록한다.

## 문서 정합성

별도 새 Luna의 최초 `python -X utf8 docs/testing/validate_docs.py`는 exit 1이었다. 상대 링크 839개·요구사항52개·시험168개를 확인했고 문서 지도의 GUI Test 문서 모음 링크 1개와 requirement coverage mismatch를 보고했다. 모음 링크를 실제 `docs/gui_test/README.md`로 복구하고 기존 RQ-52/53 정책 본문을 보존한 채 추적용 표 행을 추가했다. 시험이나 요구사항을 삭제하지 않았다. 원본 `final-20261106-exec/docs-validation-20261106-0021.log`와 exit 파일은 보존하며 수정 후 독립 재검사를 별도로 기록한다.

수정 후 같은 독립 Luna의 `.\.venv\Scripts\python.exe -X utf8 docs/testing/validate_docs.py`는 **PASS, exit 0**, 상대 링크839개·요구사항54개·시험168개·오류0이다. 검사 당시 NOT_RUN은86개였고 후속 T-168의 PASS 기록 갱신과 구분한다. 근거는 같은 디렉터리의 `docs-validation-20261106-0023.log`·`.exitcode`다. 이 검사는 제품 회귀와 별도이며 패키지 인수·실제 운영 검증을 대체하지 않는다.

## 패키지 인수 진행 이력

별도 Luna가 `.local-reports/20261105-gui-test-layout/package-20261106-001/` 아래 독립 소스·wheel·포터블 Runner를 검증했다. 다음은 단계별 이력이며 최종 판정은 뒤의 실제 pytest·무Git PATH 전체 builder 재검증을 포함한다.

- `gui-test-source-final.zip`은 91개 member의 세 경로·최소 backend 초기화·INSTALL/SHA256SUMS 구조이며 SHA256은 `f574181835cfbd72ab5f1fbe6bd4b5ad9ae6ca7594c55eddd179e4c49f15597a`다. README는 최종 승인 해시 `99bd53a0…567360`과 일치한다. 직전 소스 export의 `launch.py start/status/restart/stop`은 격리 runtime·포트18768에서 exit 0이었으며 이후 변경은 README 한 줄뿐이다. 최종 ZIP의 별도 builder 인수는 이어서 수행한다.
- 최종 wheel SHA256은 `d5f3bd10f4ea2911d482f051b5c6aa70b692b04ae487fcaeefe45b08b59630b2`다. staging·pip wheel·격리 의존성/패키지 설치·설치 import·단독 Mock demo E2E 5개·CLI help는 exit 0이다. 잘못 선택한 `gui-test-runner`와 예제의 존재하지 않는 UNC 설정에서 난 WinError53은 `gui-test` 서비스 생명주기 검증으로 세지 않는다. 이후 올바른 `gui-test.exe start/status/restart/stop`을 새 로컬 runtime·포트18831에서 실행해 **모두 exit 0**을 확인했다. 근거는 `service-lifecycle-exits.txt`와 `service-*.stdout.log`다.
- 공식 Node22.12 배포본의 SHASUM을 확인했다. 독립 source builder의 긴 경로·venv 안 fixture 설치에서 WinError206(MAX_PATH)이 발생해 `builder-final`·`builder-short-final.log`의 시도를 보존한다. 저장소 밖 실제로 짧은 공백 포함 경로의 재시험으로 환경 한계와 제품 결과를 구분하며 시스템 긴 경로 정책은 변경하지 않는다.
- 새 `dist/windows-runner/BSP-Windows-Runner.zip`은 27,933,382 bytes, SHA256 `b077f49b6ec6a7756bee0f5d1a243c2dacb54c7c733edb07ee3232b86ee66d0b`다. 고정 빌드 근거는 `portable-runner-build.stdout.log`, `portable-runner-build/build-20261105T151305269213Z`, `runner-build-info.json`이며 기존 artifact는 먼저 별도 보관했다. 최초 `python tests/portable_runner_smoke.py` 직접 호출은 exit 0이었지만 `__main__`이 없어 **시험을 수집·실행하지 않았다**. 빈 `runner-smoke.log`·`runner-smoke-final.log`는 smoke PASS 근거가 아니며 이 정정 이력을 보존한다. 실제 `pytest`로 새 EXE를 검증한 별도 결과가 도착하기 전 smoke PASS 건수를 적지 않는다. 시험은 가짜 TC/SSH와 로컬 EXE 범위이며 회사·장비 인수가 아니다.

추가로 최종 source ZIP을 공백 포함 `%TEMP%/bsp-g6-1106b/s x`에 해제한 뒤 실제 Windows PowerShell builder를 Node22.12.0/CPython3.12.10으로 실행했다. `windows-build-short-clean.log`는 **134 PASS / 4 deselected / 0 FAIL / 0 ERROR / 0 SKIP**, build-info는 complete/tests_run=true/wheelhouse_included=true, 설치된 Mock demo JSON은 simulation=true·5개 시나리오 통과를 기록한다. 예상된 FAIL 판정 시나리오도 포함한 검증이다. 이 빌드의 ZIP은16,659,178 bytes, SHA256 `0a867946be206162d6ff4c576d886559e47e038226f816e893d655e2d7dc80df`다. `.git` 폴더는 없었지만 빌드 프로세스 PATH에는 Git 실행파일이 있었으므로, 별도 `which` 명령의 Git 미검출만으로 무Git PATH의 전체 빌드 PASS를 주장하지 않는다. 새 실행 담당자가 실제 전체 builder를 Git를 찾을 수 없는 동일 자식 PATH로 다시 실행해 인수한다.

최종 export의 source health 확인은 `/api/v1/health`, `/`, 참조 JS/CSS가 각각 HTTP200이며 이후 정지 exit 0이다. 근거 `source-health3-urllib.log`는 응답 형식/크기 JSON133B·HTML389B·JS283444B·CSS25596B를 기록한다. 앞선 shell-policy로 거부된 HTTP 시도는 실행 완료로 세지 않는다.

정정 후 새 Luna가 실제 `pytest tests/portable_runner_smoke.py`를 새 Runner EXE와 짧은 임시 경로로 실행했다. `.local-reports/20261105-gui-test-layout/final-acceptance-20261106/portable.log`·`portable.xml`·`portable.exitcode.txt`는 **7 PASS, exit 0, 7.89초**를 확인한다. 경고1개는 pytest cache ACL 쓰기 경고이며 skip/fail/error는 없다. 이 실제 수집 결과를 사용하며 앞선 파일 직접 호출의 exit0을 시험 PASS로 계산하지 않는다. 무Git PATH의 전체 독립 builder 결과는 별도 확정한다.

## 최종 패키지 인수 확정

새 실행 담당 Luna가 최종 source ZIP을 해제한 공백 포함 짧은 경로 `%TEMP%/bsp-g6-1106b/s x`에서 **동일 자식 PATH의 `Get-Command git`이 `GIT_ABSENT`인 상태로 실제 전체 기본 builder를 실행**했다. Node22.12.0/CPython3.12.10을 사용했고 `SkipTests`·`SkipWheelhouse`를 지정하지 않았다. `final-acceptance-20261106/filtered-path-git-check.txt`와 `export-build.log`·`export-build.exitcode.txt`가 환경과 exit 0을 기록한다. Dashboard 소스와 `.git`이 없는 세 경로 반입본의 인수이며 별도 `which` 출력만으로 추정한 결과가 아니다.

결과는 **134 PASS / 4 deselected / 0 FAIL / 0 ERROR / 0 SKIP**, 시험16.25초·경고1개다. deselected는 기존 저장소/Git 통합 전용 선택 제외이며 해당 시험은 일반 저장소 회귀에서 유지한다. `build-info.json`은 complete/tests_run=true/wheelhouse_included=true, wheelhouse는31개 wheel, 설치된 Mock demo는 simulation=true·5개 시나리오 통과다. 앞선 MAX_PATH 실패와 Git가 존재하던 PATH의 중간 성공은 그대로 보존하고 최종 무Git 실행과 구분한다.

최종 독립 배포 ZIP은 `.local-reports/20261105-gui-test-layout/final-acceptance-20261106/export-build-output/build-a13accd3691d4a1f89c40120bcf5858f/gui-test-windows-py312.zip`, 크기 **16,659,175 bytes**, SHA256 **`438dde4f85dd970303a6f56a9417b78278c2dc238a68130c79b77273a3fa7872`**다. 같은 출력 디렉터리에 build-info·시험 XML·demo JSON이 있다. ZIP timestamps 등으로 Git-PATH 중간 산출물과 해시가 다르므로 이 최종 해시를 인수 기준으로 쓴다. source ZIP `f5741818…15597a`, 격리 설치 wheel `d5f3bd10…630b2`, 새 Runner ZIP `b077f49b…66d0b`는 앞에 적은 각각의 근거로 구분한다. 최종 source·패키지 README는 승인된 `99bd53a0…567360`과 일치한다.

이 결과로 T-166/167과 REG-0048의 무Git builder 검증, REG-0049의 패키지 README 보존 검증을 완료했다. 별도 실제 pytest의 새 Runner **7 PASS**도 함께 확인했다. 제품 소스·앱 README/VALIDATION의 승인된109개 파일은 바꾸지 않았으며 이번 최종 갱신은 실행 근거·CSV·진행 기록뿐이다. 로컬 완료 이후 CI와 main 병합은 후속 기록이며 실제 운영 정상 기준은 NONE이다.

전체 빌드·시험 로그는 [로그 규칙](../LOG_HANDLING.md)에 따라 `.local-reports/20261105-gui-test-layout/` 아래 고유 파일로 저장한다. 실패·환경 차단과 재시도를 보존한다. T-108/130/136/141/160의 실환경 인수는 NOT_RUN이며 이 변경의 로컬 결과로 대체하지 않는다. 운영 baseline은 NONE을 유지한다.
