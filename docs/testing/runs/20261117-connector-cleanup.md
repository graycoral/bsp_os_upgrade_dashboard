# 2026-11-17 · 보드 커넥터 명칭·설치 경로·스크립트 정리

- 요구사항: RQ-61/63/65/67/71, T-270~272, REG-0102/0103.
- 원본 기준: `1da1da2173c84689662de669d6a95fb8775c7037`; 최종 게시 코드·시험 고정 커밋은 `f30f57263992ce87c58bef181b6bf13456ba0f5d`다. 로컬 커밋/main 병합 대상이며 푸시·배포 ZIP 게시·실제 서비스 종료/장비 실행은 수행하지 않았다.
- 범위: 현재 사용자 문서·스크립트 표시명·frozen 호환 진입점 파일명·CLI 빌더 입력 lock/새 출력명·생성 INSTALL/README·소비 시험/PORT. DB/API/설정 파일·고정 의존성 변경 없음. 후속 사용자 지시로 명시적 로컬 강제 종료를 추가했다.
- 독립 검토: 사용자 요청의 Astra 별도 세션. [검토 기록](20261117-connector-cleanup-review.md). 실제 판정 전 NOT_REVIEWED.

## 변경과 경계

일반 사용은 플러그인과 같은 고정 커밋의 전체 소스/전체 전달 폴더 → Windows 루트 `board-connector.cmd`로 안내한다. 원본 위치·Git/소스 ZIP·전체 폴더 필요·연결 JSON 가져오기·자동 다운로드/업데이트 미제공을 명시했다. Linux 플러그인 설치와 Windows 설치는 별도이며 회사 hook은 현지 담당 범위다.

현재 문서는 `TEST_BOARD_CONNECTOR_GUI.md`, `BOARD_CONNECTOR_EXECUTION.md`, `BOARD_CONNECTOR_BUNDLE.md`로 구분하고 옛 WINDOWS_RUNNER/EDITABLE URL은 연결 안내로 남겼다. 과거 EXE 문서·날짜별 시험·고정 배포 해시·결정은 이력으로 보존한다. GUI와 CLI Host를 같은 home/포트에서 중복 기동하지 않는다. 고급 CLI 번들은 현재 브라우저 GUI가 아니며 새 기본 출력은 `dist/board-connector/BSP-Board-Connector-CLI.zip`이다. 이 실행에서 새 Windows 배포 ZIP은 생성하지 않았다.

`scripts/windows_runner_entry.py` → `scripts/board_connector_legacy_entry.py`와 소비 시험 import, `packaging/editable-windows-runner-inputs.lock.json` → `packaging/board-connector-inputs.lock.json`을 함께 바꿨다. frozen dispatch와 lock bytes·pin은 유지한다. builder의 GUIDE.md는 새 CLI 문서를 동봉한다. 생성 README의 이전 연결 토큰 입력 요구를 제거했다.

기존 설정 `windows-runner.json`/예제 파일명, API `runner`/`runner_id`/`windows-http`/`registered`, CLI `gui-test-runner`, 기본 입력 캐시·로그명·BSP_EDITABLE 환경변수·bundle v1은 호환성 때문에 유지한다. 사용자 home·SSH·TC·DB·실행/UNKNOWN 기록은 변경하지 않는다. 별도 작업 중인 제한시간 관련 7개 파일의 시작 hash/diff는 로컬에 보존했다.

## 검증

로그는 모두 `.local-reports/20261117-connector-cleanup/`의 로컬 전용이며 Git에 포함하지 않는다. 검증 결과는 아래 후속 기록에 확정한다.

1. `QT_QPA_PLATFORM=offscreen .venv/bin/python -m pytest -q -rs tests/test_board_connector_launcher.py tests/test_editable_runner_build.py tests/test_windows_runner_bundle.py tests/test_runner_ports.py tests/test_setup_runtime.py tests/test_setup_commands.py tests/test_setup_flashing_discovery.py tests/test_editable_runner_runtime.py backend/gui_test/tests/test_package.py tests/test_gui_test_layout.py`
   - 첫 sandbox 실행: 종료 1, **303 PASS / 23 SKIP / 12 FAIL** (`python-1.log`). loopback bind/프로세스 조회 제한과 기존 실패를 포함한다. 실패 기록을 보존했다.
   - 같은 명령의 권한 제한 밖 실행: 종료 1, **313 PASS / 23 SKIP / 2 FAIL** (`python-2.log`). Linux 시작 방식 fixture와 macOS process_identity 두 실패는 아래 baseline과 비교한다.
2. 고정 HEAD `1da1da2`의 git archive 사본에서 위 실패 2개만 재현: 종료 1, **2 FAIL** (`baseline-failures.log`). Linux-start 시험은 이미 관리자로 위임하는 제품과 달리 직접 API/Worker Popen을 가정했고, macOS는 `/proc` 기반 process identity를 지원하지 않았다. 기존 baseline 사본과 실패 로그를 보존했다.
3. 초기 source allowlist 103개·lock bytes/고정 hash·frozen dispatch AST·이전 중복 파일 부재·기존 WIP 7개 hash 보존: **PASS** (`inventory-1.json`). 강제 종료 파일 추가 후 최종 범위 검사와 격리 후보 검증은 아래 후속을 따른다.
4. 문서 최초 검사: **PASS**, 상대 링크 1830개·요구사항70·시험270·오류0 (`docs-1.log`). 강제 종료 요구사항/문서 추가 전의 검사이며 최종 검사는 별도 기록한다.

## 제약

실제 Windows CMD/PowerShell와 새 Windows CLI ZIP의 빌드·오프라인 실행은 NOT_RUN이다. 회사 플러그인·Linux SSH·UART/USB·TC·장비·ACON 인수도 NOT_RUN이다. 과거 Windows/회사 PASS나 다른 기능 WIP의 결과를 이번 정리의 신규 근거로 재사용하지 않는다. 문서 링크 검사는 제품 통과가 아니다.

## 후속: 명시적 강제 종료와 플러그인 설정 안내

추가 사용자 지시로 Linux `bash run.sh force-stop`/`manage.py force-stop`, Windows `board-connector.cmd --force-stop`을 구현했다. D-77/RQ-71/T-271~272. 설치/GUI/장비 연결 없이 저장된 생성 세대를 pin하고 해당 로컬 관리 트리만 종료한다. Linux pidfd+SIGSTOP 완료 확인, Windows process handles+부모 종료 후 자식 재탐색, 자식 pin 이후 PPID 재검사, 즉시 checkpoint·pending/start barrier를 적용한다. Monitor owner/API/Worker와 Windows SSH identity를 영속하며 기존 v1 endpoint에 transport만 선택적으로 추가했다. DB/설정/예약/UNKNOWN 기록은 보존한다. 실제 서비스를 종료하지 않았다.

플러그인 `connect`/inventory/mirror의 상태 조회와 회사 UI 적용의 차이, Linux 공통 설정과 Windows 로컬 JSON의 실제 적용 기준·기본 경로·미설정 초기값을 사용/API 문서에 추가했다. 회사 플러그인 자체는 이 저장소에 없으며 실제 표시 여부는 NOT_RUN이다.

### 실패·수정·재검증

- `force-1.log`: sandbox 실행 **213 PASS / 22 SKIP / 13 FAIL**, 종료1. loopback 권한 제한과 기존 stale fixture를 포함한다.
- `force-2.log`: 권한 제한 밖 실행 **221 PASS / 22 SKIP / 5 FAIL**, 종료1. 4건은 새 SSH receipt가 요구하는 PID가 기존 Transport fixture에 없었고, 1건은 기존 Linux-start fixture였다. fixture에 실제 Popen 속성을 추가하고 Linux 위임 시험은 관리자 start 인자/runtime/config 보존·중복 API/Worker 미기동을 검증하도록 수정했다. 실패 이력은 보존했다.
- `force-unit-3.log`: **15 PASS / 1 FAIL**. 즉시 checkpoint가 첫 pin에서 실패하도록 바뀌어 열린 handle 수를 고정2개로 가정하던 시험이었다. 열린 handle 전체 close와 kill 미호출을 검증하도록 수정했다. `force-unit-4.log`: **16 PASS**.
- `integration-3.log`: 현재 작업 트리의 관련 17개 파일 모의 회귀, 종료1, **553 PASS / 23 SKIP / 1 FAIL**. 남은 실패는 baseline과 동일한 macOS `/proc` 미지원 process_identity 시험이며 skip 추가·기대값 완화로 숨기지 않았다. 이 실행은 최종 저장소 격리 후보 검증을 대체하지 않는다.
- Astra 초기 독립 시험 **12 PASS**, 초기 리뷰 **CHANGES_REQUESTED**. REG-0103의 자식 PID 재사용·post-exit checkpoint 누락·CLI start barrier를 수정하고 신규 회귀를 추가했다. 독립 최종 판정은 [리뷰 기록](20261117-connector-cleanup-review.md)에 따로 남긴다.

최종 제품/시험 hash manifest, 격리 후보 회귀·문서 검사와 독립 최종 판정은 이어서 확정한다. Windows handle/PPID 동작의 1차 근거: [PROCESS_INFORMATION](https://learn.microsoft.com/en-us/windows/win32/api/processthreadsapi/ns-processthreadsapi-process_information), [Toolhelp parent PID/handle 수명](https://devblogs.microsoft.com/oldnewthing/20150403-00/?p=44313). 이 근거는 실제 Windows 실행 시험을 대신하지 않는다.

## 최종 격리 후보 검증·독립 판정

다른 작업의 미커밋 timeout/telemetry 변경을 제외하고 기준 HEAD 위 이번 소유 경로 58개만 적용한 Git 독립 후보를 검증했다. 실제 커밋에도 같은 제품/시험 bytes를 사용한다.

- 제품·시험 manifest: 22개(삭제2 포함), SHA256 `685e5cd7d416a9511d525760294c84266273eeabe35756a6723fcf02e18b825b`. 상세 `.local-reports/20261117-connector-cleanup/product-manifest.json`은 로컬 전용이다.
- 최종 명령: 위 통합 17개 시험 파일에 `tests/test_force_stop.py`를 포함한 후보 실행에서 `-k 'not test_process_identity_detects_live_child_and_does_not_accept_dead_pid'`를 적용했다. 종료0, **553 PASS / 24 SKIP / 1 DESELECTED** (`candidate-python-4.log`). DESELECTED 1건은 앞서 현재/고정 HEAD에서 모두 실패한 Mac `/proc` 미지원 시험이다. 시험 코드의 기대값 완화나 skip 추가는 하지 않았다.
- 24 SKIP은 실제 Windows 전용23건과 후보에 미생성 UI 자산이 없어 건너뛴 전체 UI 전달 인수1건이다. 작업 트리의 미리 빌드된 자산을 새 후보의 제품 검증처럼 복사하지 않았다. 소스/lock/CLI bundle 재포장·패키지와 GUI Host 모의 회귀는 위 553건에 포함된다. 새 ZIP·UI 배포 생성 완료를 주장하지 않는다.
- `force-unit-5.log`: 명령 자체 KeyboardInterrupt 직전/직후 영속 phase 회귀까지 **18 PASS**.
- Astra 최종 **APPROVED**, 독립 후보 시험 **51 PASS / 12 SKIP**, 제품·시험 manifest 대조 불일치0. [리뷰 이력](20261117-connector-cleanup-review.md). 실제 OS/회사 인수는 아니다.
- 원본 작업 폴더의 `docs-2.log`는 동시 진행 중인 별도 telemetry 문서의 미완성 링크/등록으로 FAIL이었다. 그 변경은 이번 격리 후보·커밋 범위에서 제외하며 최종 문서 검사는 아래 별도 확정한다.
- 초기 WIP 7파일의 첫 inventory hash는 보존했다. 이후 다른 세션이 TestPage.tsx 등 별도 작업을 진행한 차이는 이번 수정으로 덮어쓰지 않았다. main 반영 전후 작업 폴더/비대상 index 보존을 별도로 확인한다.

Windows post-exit 탐색 오류뿐 아니라 명령 중단·Wait 전후에도 Terminate 전 phase를 영속한다. 완료 스캔과 미완료 세대를 구분하고 미확인 트리는 자동 성공으로 바꾸지 않는다. 모든 로컬 프로세스 확인을 장비/외부 BSP 완료로 확대하지 않는다.

## 최신 main 통합 후 최종 검증

검토 후 다른 세션의 자동 COM 변경 `59af913`/`c6411a8`/`12a82a6`이 main에 반영되어 별도 Git clone에서 검증한 feature와 합쳤다. 제품 충돌은 없었고 문서 append 충돌7개는 양쪽 절·T-273 이력을 보존했다. telemetry·기존 timeout WIP는 포함하지 않았다.

- 첫 통합: `merged-python-5.log`, **595 PASS / 25 SKIP / 1 DESELECTED / 1 FAIL**, 종료1. 이전 포트 시험 fixture가 serial 필드 없이 시작해 새 main의 의도된 proxy 자동 정규화와 충돌했다. fixture만 이미 정규화된 proxy로 준비하고 config bytes 완전 동일·포트·터널·종료 신호 assertion은 보존했다. native→proxy 이전은 자동 serial 시험에서 검증한다.
- 수정 후 같은 통합20개 시험 파일: `merged-python-6.log`, 종료0, **596 PASS / 25 SKIP / 1 DESELECTED**. 이전 Mac /proc 제약1건 분리는 그대로이며 실패 원본도 유지한다. SKIP은 실제 Windows 전용24건과 후보에 미생성 UI 자산으로 인한 전체 UI 전달 인수1건이다.
- 통합 문서 검사 `merged-docs-4.log`: **PASS**, 상대링크1880개·요구사항71·시험273·오류0. 최종 pin 기록 후 다시 검사한다.
- Astra 병합 delta **APPROVED**, 독립 **75 PASS / 3 SKIP** (`astra-merge-delta.log`). setup_runtime/Windows bundle/ports fixture와 자동 COM·force barrier·transport receipt를 함께 검토했다. 앞선 독립 sandbox6 FAIL/14 ERROR는 loopback 제약이며 제한 밖 재실행으로 구분했다.
- 최종 통합 제품/시험 manifest22개 SHA256: `dc469cf70b014af159672cba9e8108ca476c4c97a5ef8727d7e0d647c049af6e`. 최초 승인 manifest와의 차이는 이미 검토한 자동 COM 연동 및 포트 fixture이며 나머지 제품 bytes는 유지한다. 실제 Linux/Windows·회사 장비·새 ZIP T-272는 NOT_RUN이다.

고정 코드·시험 커밋: `af269448dfbdbc426d0403738e82453118cf8638`. 이 문서 pin 후속은 제품/시험 bytes를 변경하지 않는다. 원본 작업 폴더의 다른 WIP·스테이징을 유지하여 로컬 main에 반영하며 원격 push는 별도다.

## 최종 main 이동 보존 확인

반영 직전 다른 세션의 Sonnet/사용량·시간 커밋 `75751f3`/`41ba537`도 main에 들어와 그 이력을 그대로 합쳤다. 이번 제품·시험22개 manifest는 승인·통합 검증본과 **불일치0**이며 별도 기능을 되돌리지 않았다. 이 최종 트리에서 같은20개 회귀를 다시 실행했다: `latest-python-7.log`, **596 PASS / 25 SKIP / 1 DESELECTED**, 종료0. 기존 Mac /proc 실패1건 분리와 실제 OS/회사 T-272 NOT_RUN 경계는 동일하다.

`latest-docs-6.log`: **PASS**, 상대링크1902개·요구사항72·시험277·오류0. 추가된 요구/시험은 보존한 다른 main 작업의 것이며 이번 force-stop 인수를 확대한 것이 아니다. Git 작업 폴더의 비대상 파일/스테이징을 보존해 로컬 main만 전진시킨다. 원격 push·실제 서비스/장비 강제 종료는 수행하지 않는다.

## 사용자 후속: BAT 클릭 실행·서버 포트

사용자가 제시한 클릭 실행 예시의 SystemRoot/인자 오기를 바로잡아 루트 `board-connector.bat`를 추가했다. ASCII BAT는 AutoRun·지연 확장을 끈 system CMD에서 기존 CMD를 호출하며 인자·종료 코드를 보존한다. 설치/GUI 로직을 복제하지 않는다. 최신 main f0fd97c의 포트 저장 기능을 유지해 `board-connector.bat --server-port 8765`로 저장하고 이후 더블클릭은 저장값(최초8766)을 재사용한다. force-stop/포트 설정 병용은 거부한다. 전체 source export에 BAT를 포함한다.

- `bat-unit-9.log`: **137 PASS / 22 SKIP**, 종료0.
- `bat-full-10.log`: 최신 main·BAT 통합21개 시험 파일, **623 PASS / 33 SKIP / 1 DESELECTED**, 종료0. 기존 Mac /proc 실패1건과 그 실패 이력은 앞선 설명대로 분리한다. SKIP은 Windows 전용32건과 후보 미생성 UI 자산 전달 인수1건이다.
- Astra BAT/port delta **APPROVED**, 독립 **90 PASS / 21 SKIP**. 인용·인자·종료 코드·readonly force 분리·export BAT bytes 및 CMD 포함을 확인했다. 제품 파일·실제 서비스/장비 수정·종료 없음.
- Windows BAT/CMD의 LF/CRLF·공백/기호/한글·서버 포트/home·exit0/17 계약을 확장했으나 Mac에서는 **T-279 NOT_RUN**이다. 사용자가 보고한 유사 예시 성공을 새 파일의 정식 Windows 인수 PASS로 바꾸지 않았다.
- 최신 main의 포트 시험은 정규화된 전체 config와 원본 backup 및 Linux 관리자 전체 argv/kwargs 검증을 보존했다. 중복 API/Worker Popen도 거부하도록 검증한다.
- 최종 제품/시험 manifest 25개, SHA256 `c29c13af23043b85e82b8b66df90d816d4b4759846073c205a7ec0c117a3bf28`. main 이동을 감지한 앞 CAS는 원본 main/index/작업 파일을 변경하지 않고 중단했다. 원본의 별도 TC 상태 polling WIP가 supervisor.py에 추가되어 그 미커밋 부분도 이번 tree에서 제외·보존한다.

최종 BAT 포함 코드·시험 고정: `9450e9f30e95e2c956f9890b3512ba2b80e5f933`. 이전 단계의 고정 SHA·실패 로그는 당시 증거로 보존하며 이번 최종 manifest25항목과 구분한다. 문서 pin 후속은 제품 bytes를 변경하지 않는다.

## 원격 main 게시 · GitHub API 경로

HTTPS Git push는 인증 정보 부재로 실패하여 연결된 GitHub API를 사용했다. 로컬62d6b52의 검증 트리에서 test_force_stop.py의 Windows 시험 이식성 fixture만 보완했다. synthetic Linux signal 번호와 플랫폼 공통 배타 lock을 주입하며 runtime 코드·기대값·skip 조건은 변경하지 않았다. Astra 독립 재검토 APPROVED·18 PASS, 게시 후보 전체 재시험 **623 PASS / 33 SKIP / 1 DESELECTED**(`.local-reports/20261117-connector-publication/regression-1.log`, 로컬 전용)다. 실제 Windows/회사 T-279/T-272 NOT_RUN은 유지한다.

61개 tree 변경의 Git blob SHA를 대조하고 API code tree `87402ebf5b2d1242e4ac57b16f5a75cbe8b6f889`가 검증 후보와 동일함을 확인했다. 공개 전달용 코드·시험 pin은 `f30f57263992ce87c58bef181b6bf13456ba0f5d`다. API 생성으로 로컬 미게시 commit SHA와 달라지지만 제품 bytes를 바꾸지 않는다. 이전 로컬 commit/실패 로그는 과거 근거로 보존한다. 문서 pin 후속은 제품/시험 bytes를 변경하지 않으며 PR로 main에 반영한다. 별도 TC 상태/timeout WIP는 게시 범위에 포함하지 않는다.
