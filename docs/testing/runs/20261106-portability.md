# 2026-11-06 GUI 호스트 이식·UI 동일성·중복 정리

요구사항 RQ-57 / 결정 D-61 / 구현 DEVPORT02 / 시험 T-183~190. 사용자 승인 범위는 이식 결함 구현과 확인된 중복 raw 삭제다. 현재 미커밋 작업 트리이며 HEAD를 고정 구현 커밋으로 표시하지 않는다. 기존 RQ-55/56·사용자 설정·승인된 Runner ZIP과 실패 이력을 보존한다.

## 구현과 검증 경계

공통 Python의 호스트 역참조를 host factory/reference로 분리하고 public UI index·GuiTestHost/context·동일 CSS/token을 제공한다. `--base`는 파일 수집/출력 전 거부하고 source-only `--host-integration --target bsp-dashboard-host-v1`로 현재 세 roots·검토용 host-reference·provenance/파일 hash manifest·독립 문서·전체 entry checksum을 내보낸다. standalone/stage-wheel은 Git 독립 계약을 유지한다. REG-0065/0066과 source 결함 REG-0067/0068은 수정 후 별도 시험 근거를 연결한다.

현재 상태: **T-183~189 로컬 PASS / 독립 리뷰 APPROVED / T-190 NOT_RUN**. 구현 직후(과거 상태)는 T-183~190 NOT_RUN / 독립 리뷰 NOT_REVIEWED였다. 실제 회사 UI·API 인증·GitHub/Gerrit·SSH/TC/COM/보드·Jira 인수는 NOT_RUN이다. 기존 승인 EXE는 source_snapshot_v1 지원 근거가 없는 배포본이며 새 바이너리를 만들거나 교체하지 않는다.

전체 새 개발 로그·JSON·스크린샷은 `.local-reports/<run-id>/` 로컬 전용이며 저장소에 포함하지 않는다. 실행 담당자가 기록할 시험 의도는 TEST_CATALOG T-183~190을 따른다. 기존 T 결과는 변경하지 않는다.

## 확인된 중복 raw 정리

아래 표는 압축 해제 bytes와 raw 전체 bytes 및 SHA256 일치를 확인한 결과다. raw 7개만 삭제하고 .gz·전후 manifest·독립 lockfile·namespace staging·approved ZIP과 역사적 시험 결과는 보존한다. 문서 경로만 .gz로 갱신하며 기존 FAIL/PASS 결과를 다시 해석하지 않는다.

검증 명령: Python gzip.decompress + raw 전체 bytes 비교 + SHA256 비교, exit 0, 7/7 일치. 삭제 이유는 같은 bytes의 raw/.gz 중복이며 .gz는 그대로 보존한다. 경로는 모두 `docs/testing/runs/20261104-ui-finish-evidence/` 아래다.

| 삭제한 raw | 보존 .gz | decoded bytes | raw = decoded SHA256 |
|---|---|---|---|
| final-build-dashboard.log | final-build-dashboard.log.gz | 834 | `f475cb2f8644319311378831662162502573343af541a87a30d27a4348127f75` |
| final-build-gui-test.log | final-build-gui-test.log.gz | 908 | `bbfaba8171ba9fabf3a334561477190613e39a09db78678cec648ad6af8f0cc8` |
| final-workflow-diagram-missing-browser.log | final-workflow-diagram-missing-browser.log.gz | 146226 | `599e23db54d8b96725c572e49d5155b142e5d3a1c15cc63991b9c56808e16fd8` |
| final-workflow-diagram.log | final-workflow-diagram.log.gz | 19724 | `b7b9e09d047a315c6932c9d1ea8fcf8436ae133204d31ccc50369adc7039b8f3` |
| pre-sync-build-dashboard.log | pre-sync-build-dashboard.log.gz | 834 | `5b71c92d80c7d2a8ce260d9ff236830b759907407918404f2cbe5626772944f4` |
| pre-sync-build-gui-test.log | pre-sync-build-gui-test.log.gz | 908 | `7ca566fe85836ea375f52c3e065376c8649c51ba7341ca34da1a765c1ce50ec1` |
| pre-sync-workflow-diagram.log | pre-sync-workflow-diagram.log.gz | 19542 | `47b8dbb3b43fe386f0cf8008c692b818260fbc219023eafd0cd6dbda116d1cc7` |

경로 참조 갱신: 기존 문서 참조 없음. 기존 결과·실패 이력은 변경하지 않았다.

단독 API 호환: 호스트 demo router를 공통 router에서 분리한 뒤에도 standalone의 기존 demo/jobs URL은 GET 빈 목록·개별 조회/변경 TestError 거부 계약을 유지하도록 로컬 disabled router를 조립한다. 공통 router에는 호스트 import/engine 접근이 없다. source demo는 `--dashboard`에서만 backend 호스트를 지연 import한다. T-184 재시험에 포함한다.

구현 담당 기본 검사: package.py와 standalone/server.py를 Python compile로 구문 확인, exit0; `git diff --check` exit0. 로컬 전용 로그는 `.local-reports/devport02-delivery-sanity/syntax.log`·`diff-check.log`다. 이 기본 검사 자체는 제품 시험/독립 리뷰 결과가 아니다.

## 후속 리뷰 · ZIP 시험 명령의 호스트 의존 범위

REG-0066 후속 P2에서 기존 `python -m pytest backend/gui_test/tests -q` 안내가 extracted-only ZIP에 없는 backend.api/main을 top-level import하는 시험 때문에 collection에 실패함을 확인했다. generated INSTALL/HOST_CONTRACT/manifest는 하나의 명시적 portable 명령을 공유하도록 수정했다. 10개 portable 파일을 수집하고 호스트 API demo/source 연결 및 full-host 재패키징 3개 사례만 -k로 제외한다. selected 파일 top-level imports와 공유 helper가 canonical roots에 있음을 확인했다. 제외는 호스트 의존 범위 구분이며 기존 시험 assertion·PASS/FAIL은 변경하지 않는다. 전체 저장소 회귀는 모든 제외 사례와 host-only live_view/module_selection을 포함해 별도 실행한다. 최종 extracted-only 시험 결과는 아래에 기록한다.

## 후속 전달 보완 · shared fixture의 실제 반입

이전 host ZIP은 shared fixture 비교를 안내했으나 fixture가 원본 workflow_diagram/tests에만 있어 회사에서 그대로 열 수 없었다. 기존 canonical portable-ui-host.tsx를 host ZIP ui-verification에 포함하고 import 한 곳만 이동 대응한다. 생성한 index.html/vite.config.mjs/README와 함께 기존 apps/gui-test npm lock/toolchain으로 수동 preview를 연다. manifest에 canonical/exported hash·치환·네 파일·정확한 command/읽기 전용 URL을 기록한다. 별도 UI 구현·전체 workflow·apps/web/backend·Playwright 의존성을 추가하지 않는다. 최종 실행 결과는 아래에 기록하며 회사 인수는 NOT_RUN이다.

## 최종 독립 로컬 검증과 리뷰

별도 unit_test_execution_reporting 담당 GPT-6 Luna Low 실행 및 복구 감사 기준이다. CSV의 executed_at은 최종 package 로그 exit.txt의 기록 시각인 종합 로컬 검증 완료 시각이며 개별 명령 시각은 아래 로그 디렉터리 ID와 원본 기록을 따른다. 로그·JSON·스크린샷은 `.local-reports/portability-exec-20261106-112641-952/`에만 보존한다. 코드 193개 manifest SHA256 `1fd2ed82201670f1e2d667fcc08f9b2f5f14b74deeec2599b698f7842c261b18`, 시험 63개 manifest SHA256 `ca6aad3a3efac9f6f544df5a4314f8a2c3caaf16d67b72a514b108a73b355f96`이며 `.local-reports/portability-final-manifest-20261106-114135/`에 있다. HEAD `cd124aef4528094eb4eda53143435dfae9404704`는 ancestry일 뿐 고정 릴리스 커밋이 아니다. 최종 manifest 이후 제품 파일 변경 없음이 감사되었다. 기준 버전 변경은 NONE이다.

| 로컬 로그 하위 디렉터리 | 결과 |
|---|---|
| focus; focus-rerun-20261106-112724-660 | 113 PASS/2 SKIP 후 117 PASS/4 SKIP |
| regression-python-20261106-113139-562 | 415 PASS/2 SKIP |
| workflow-rerun-20261106-113619-758 | 74 PASS, portable 17 포함 |
| settings-source-browser-retry-20261106-113341-562 | 15 PASS |
| standalone-browser-20261106-113408-247 | 18 PASS |
| browser-20261106-113019-141; browser-rerun-20261106-113246-533 | portable/module 최초 14 PASS/3 FAIL 후 17 PASS |
| build-dashboard-20261106-113224-864; build-gui-20261106-113235-936 | 양 UI build exit 0 |
| final-portable-smoke-20261106-113810-969 | 추출 ZIP portable 명령 227 PASS/4 deselected |
| final-wheel-smoke-20261106-113916-467 | 격리 wheel build/install/import gui_test/demo exit 0 |
| final-package-regression-20261106-114129-140 | 19 PASS/2 SKIP, exit 0 |

최종 package 회귀는 `python -m pytest backend/gui_test/tests/test_package.py tests/test_gui_test_layout.py -q --basetemp <unique Temp>`로 실행했다. Windows symlink 불가로 skip했으며 Starlette httpx deprecation 및 pytest cache 권한 경고가 있었다. workflow 74와 그 안의 portable 17은 중복 합산하지 않는다.

최초 portable/module 실패 중 두 건은 전역 heading CSS로 인한 1024/1440 버튼 Y 차이 7.5px이며 scoped 상속 font와 native heading scale로 수정했다. 세 번째는 SSR 시험의 browser alias에서 ReactCJS undefined가 발생한 harness 문제로 별도 `configFile:false`/externals를 적용하고 public index 전체를 browser globals 없이 검사했다. 최초 실패 로그는 보존하지만 같은 경로에 덮어쓴 Playwright trace/JSON 전체가 보존되었다고 주장하지 않는다.

최초 독립 Sol High 리뷰는 `ownsSession` 누락 시 lease 가능성과 export된 전체 suite의 host 모듈 누락을 지적해 CHANGES_REQUESTED였다. 수정 후 APPROVED, 후속 CSS/SSR 범위 리뷰와 최종 fixture exporter 리뷰도 APPROVED다.

최종 `final-delivery-20261106-114110-600`의 standalone ZIP은 106 entries/105 checks, 305805 bytes, SHA256 `5dd38cac66b41b254e22509e2b9aaf6c3356dbc252aeaa3a599b2ee4e1bafc5e`; host ZIP은 110 entries/109 checks, 222070 bytes, SHA256 `3958632fabe74cde412d3c3925551805581a577efa52ace70771c98291c5afab`이다.

`host-ui-fixture-20261106-114004-389/host-integration.zip`의 ui-verification 파일은 index.html, vite.config.mjs, README.md, portable-ui-host.tsx다. canonical fixture에서 import `../../packages`만 `../packages`로 치환했고 해시와 치환은 manifest에 있다. 추출 ZIP에서 `node apps/gui-test/node_modules/vite/bin/vite.js --config ui-verification/vite.config.mjs --host 127.0.0.1 --port 18779 --strictPort` 실행 후 `?observer&terminal`을 Chrome 1440/375에서 확인했다: case 표시, action 비활성, API 요청 0. 설치된 apps/gui-test toolchain을 node_modules junction으로 재사용했으며 설치/네트워크는 없었다. browser-result.json과 screenshot은 해당 로컬 fixture 디렉터리에 있다. 프로세스 종료 및 listener 부재를 복구 감사에서 확인했다. 회사 UI 배포 검증은 아니다.

실제 외부 API 인증·SSH·보드·Jira·모델·Git 원격·회사 UI 인수는 NOT_RUN이다. 승인된 Runner 바이너리는 source_snapshot_v1 지원 증거가 없으며 교체하지 않았다. 문서 검사 `final-doc-check-20261106-114145-141`은 결과 갱신 전 PASS였다. 이후 검사에서는 T-183~189의 executed_at 누락 7건으로 FAIL했고, 시각을 보완한 뒤 재검사는 별도로 실행한다.


Final docs validation command `.venv/Scripts/python.exe -X utf8 docs/testing/validate_docs.py` exited 0: 949 links, 57 requirements, 190 test cases, 84 NOT_RUN, zero errors; full output: `.local-reports/portability-docs-final-20261106-114813-238/docs-full.log`.
