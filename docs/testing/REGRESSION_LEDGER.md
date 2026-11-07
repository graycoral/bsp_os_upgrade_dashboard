# 회귀·결함 기록

## REG-0074 · 이식 패키지에서 목록 설정 모듈 누락

상태: **LOCAL_VERIFIED / independent review APPROVED / CI_RETEST_PENDING**. RQ-57/58. PR #18의 첫 Linux CI는1123 PASS/15 SKIP/1 FAIL이었다. 기존 RQ-58의 `core.manager`가 루트 `catalog_settings.py`를 import하지만 canonical `package_files()`의 명시적 루트 파일 목록이 이를 포함하지 않아 실제 추출 host ZIP의 runtime import가 ModuleNotFoundError로 실패했다. 기존 `test_actual_host_archive_is_self_contained_and_hashes_every_entry`가 재현했으며 단순 모의 fixture 실패로 제외하지 않는다.

지정 Terra Low가 허용 목록에 필요한 단일 모듈만 추가했다. 동일한 수집 경로를 사용하는 host source ZIP·standalone source·stage wheel에 적용하며 경로·symlink·파일 제한은 유지한다. 별도 Luna의 package/layout 시험19 PASS/2 SKIP와 독립 Sol High APPROVED를 확인했다. UI·API·DB·서비스 실행 코드는 변경하지 않는다. 수정 커밋은 이 항목을 처음 포함하는 커밋이며 원본 CI 로그와 별도 package 재시험 근거는 [실행 기록](runs/20261106-compact-test-settings.md) 및 `.local-reports/compact-test-settings-20261106/`에 보존한다.

## REG-0073 · 결과 화면 복귀 후 비동기 설정 오류 숨김

상태: **LOCAL_VERIFIED / independent review APPROVED**. RQ-55/D-59 설정 간결화의 새 독립 검토에서 발견했다. Test 현황 내부에서 소스 적용을 시작하고 `← 결과로 돌아가기`를 누른 뒤 요청이 실패하면, 처음 구현한 reveal 함수가 카테고리와 바깥 접기만 열어 숨겨진 설정 작업 영역의 오류가 보이지 않았다. 현재 activity/presentation ref를 확인해 활성 로컬 문맥이면 설정 작업 영역도 열도록 수정했다. 숨겨진 다른 탭이나 전역 문맥의 이동은 강제하지 않는다.

T-181 지연 실패 회귀는 결과 화면 이동 후 오류·설정 카테고리·입력 보존과 적용 소스 불변을 확인한다. 관련 설정·소스·조회28개가 별도 Luna 실행에서 PASS했고 새 독립 Sol High 재검토도 APPROVED다. 수정 기준은 이 항목을 처음 포함하는 커밋, 실행 ID는 `20261106-compact-test-settings`, 상세 근거는 [간결화 실행 기록](runs/20261106-compact-test-settings.md)을 따른다. 다른 동시 작업의 REG-0072는 재사용하지 않는다.

## REG-0070 · 전체 환경 설정에 Test 작업 화면 노출

상태: **LOCAL_VERIFIED / independent review APPROVED**. RQ-55/D-59. 최초 구현은 전체 설정에 TC 카탈로그/선택 편집까지 제공하는 것으로 해석해 전역 TestPage의 사이드바를 강제 표시했다. 사용자는 설정 항목만 모으라고 정정했으므로 TC 목록·실행 작업 화면은 전역에서 제외했다. 같은 편집기와 상태는 유지하고 전역 사이드바를 hidden으로 처리하며 설정을 한 열로 표시한다. 방지 시험은 T-170/172의 전역 작업 UI 비표시·지역 TC 상태 보존·동기화 확인이며 설정/소스16·단독18·실제 화면 확인이 PASS다. 합성65 PASS/1 TIMEOUT 후 실패 사례 단독1 PASS도 보존한다. 기준 `d8bc08d`, 수정 커밋은 이 항목을 처음 포함하는 커밋이며 [수정·재시험 기록](runs/20261106-settings-only.md)을 따른다. 다른 동시 작업의 REG-0065~69 번호는 재사용하지 않는다.

REG-0061~64 final isolated retest: run `20261106-settings-sync-isolated-112705720-final`, source47 and affected backend355 PASS/2 SKIP; browser105 PASS; fresh independent review APPROVED. Initial failures remain in [the run record](runs/20261106-settings-sync.md). The fixing revision is the first feature commit including these entries.

## REG-0064 · Windows 긴 스냅샷 경로의 적용 후 재조회 실패

상태: **VERIFIED / isolated regression PASS / independent review APPROVED**. RQ-56/T-177/178/179. 신규45개 집중 시험은 통과했으나 더 긴 외부 임시 경로의 전체 회귀에서 소스 적용 후 manifest 재조회4건이 실패했다. 임시 prepare 디렉터리에서 파일을 쓸 때보다 최종64자리 snapshot 디렉터리로 이름을 바꾼 후 자식 경로가 길어져 Windows MAX_PATH 경계에 도달했다. 같은 파일은 일반260자 경로에서 WinError3, 확장 경로에서753바이트 읽기에 성공해 실제 제품 결함으로 확인했다. 단순 시험 환경 오류로 제외하지 않는다.

원래 실패는 `.local-reports/settings-sync-20261106/110151656-source/backend-regressions-final.log`, 원인 확인은 `.local-reports/source-longpath-triage-20261106/inspect.log`에 로컬 전용 보존한다. 내부 snapshot 경로에 UNC를 고려한 Windows 확장 경로를 사용하고 최종 게시된 manifest·파일을 active 포인터 변경 전에 다시 확인하도록 수정한다. 별도 시험 작성자의 `test_sources.py` 회귀는300자 이상 manifest 경로에서 적용·재시작 조회·archive 전송·수신·attempt 복사와 정확한 보조 파일 bytes를 요구한다. 경로를 줄이거나 skip하지 않는다. 수정 커밋과 재시험 결과는 [이번 기록](runs/20261106-settings-sync.md)에 추가한다.

## REG-0062 · Windows 전송의 디렉터리 대소문자 별칭

상태: **VERIFIED / isolated regression PASS / independent review APPROVED**. RQ-56/T-178. 최초 구현은 파일 경로 전체의 casefold 중복만 검사해 `Foo/a.py`와 `foo/b.py`를 허용했다. Windows에서 두 디렉터리가 합쳐져 전송 성공 후 실행 복사 시 SOURCE_CHANGED가 발생할 수 있었다. 독립 리뷰의 `.local-reports/source-review-20261106-casing/full.log`에 재현을 보존한다.

공통 `validate_paths`가 모든 경로 접두어의 원래 대소문자와 파일/디렉터리 유형을 비교하도록 수정하고 manifest 생성과 수신 검증 모두에 적용했다. `a`와 `a/b` 같은 유형 충돌도 거부한다. 별도 리뷰의 `.local-reports/source-review-20261106-final/full.log`는 양쪽 진입점 거부를 exit0으로 확인했다. 방지 시험은 `backend/gui_test/tests/test_source_snapshots.py`의 접두어 충돌 사례이며 독립 실행 결과는 [이번 기록](runs/20261106-settings-sync.md)에 추가한다. 수정 커밋은 이 항목을 처음 포함하는 기능 커밋으로 고정한다.

## REG-0063 · 기본 공유 소스로 되돌리기의 API 종류 누락

상태: **VERIFIED / isolated regression PASS / independent review APPROVED**. RQ-56/T-177/180. 통합 중 UI는 `kind=legacy`로 기본 소스 복귀를 요청하지만 최초 API 입력 종류가 폴더/Git만 허용해 422가 발생했다. API·서비스의 legacy 검사/버전 CAS 적용을 추가했다. 원래 고정 스냅샷과 과거 Run은 삭제하지 않는다. 별도 리뷰의 `.local-reports/source-review-20261106-final/full.log`에서 재확인했으며 신규 서비스·브라우저 복귀 시험은 독립 실행 결과를 [이번 기록](runs/20261106-settings-sync.md)에 남긴다. 수정 커밋은 이 항목을 처음 포함하는 기능 커밋으로 고정한다.

## REG-0061 · 설정 동기화 브라우저 시험의 접근성 이름·option 선택자

상태: **VERIFIED / isolated regression PASS / independent review APPROVED — 시험 코드 결함**. RQ-55 T-169/173/175의 초기 Chrome 실행은 4 PASS/3 FAIL이었다. `JsonInput`의 오류 도움말이 감싸는 label의 접근성 이름에 추가되므로 잘못된 입력 후에는 정확 일치 이름으로 필드를 찾을 수 없었다. 저장된 연결 option은 텍스트로부터 value가 정해지며 HTML value 속성을 따로 쓰지 않는다. 이를 명시적 속성 선택자로 찾은 것도 원인이다. 화면의 입력·오류 포커스·저장은 초기 실패 스크린샷/trace에 유지되어 있었다.

별도 시험 작성자가 label의 안정적인 접두어와 이름 있는 option/selectOption을 사용하도록 수정했다. 원래 입력 보존·포커스·저장/재접속 검증은 유지했으며 비활성 초기 조회·폴링·접기 저장소 예외·중복 ID 시험을 보강했다. 수정 커밋은 이 항목과 시험 수정을 처음 포함하는 커밋으로 고정한다. 최초 실행 로그는 `.local-reports/settings-sync-20261106/104929770/`에 로컬 전용 보존한다. 재시험 근거는 [설정 동기화 실행 기록](runs/20261106-settings-sync.md)에 추가한다. 기본 Playwright 캐시 부재로 페이지 실행 전 중단된 이전 시도는 환경 실패로 구분한다.

## REG-0060 · create 재접수에서 frozen 도구 경로 재탐색

상태: **VERIFIED — 로컬·모의 범위 / 독립 검토 APPROVED / 최종 CI SUCCESS**. PR #14 최초 CI `42071298278`, head `247d08080dee0f47f667afd6f487ab4ff603e445`의 Linux에서 기존 `tests/test_native.py::test_t100_new_job_freezes_resolved_paths`가 실패했다. Linux 결과는1 FAIL/949 PASS/15 SKIP이며 이후 demo/browser/package는 SKIPPED다. Windows package의343 PASS/3 SKIP 및 설치 demo5 PASS와 구분한다. [현재 실행 기록](runs/20261106-orchestration-v2.md)에 실패와 후속 수정을 보존한다.

재현: 도구 경로를 고정해 create를 성공시킨 뒤 PATH에서 도구를 제거하고 같은 명령 키/내용을 재요청한다. 원인은 `Engine.create`가 저장된 create 응답 조회 전에 `prepare_job_profile`의 PATH probe를 반복한 것이다. frozen job/replay의 멱등성 위반이며 환경 한계로 제외하지 않는다.

수정: 공통 command digest/replay 로직으로 읽기 전용 선조회를 수행하고 외부 caller의 payload는 deepcopy한다. 도구 probe는 DB transaction 밖에 유지하며 최종 transaction에서 키/내용과 경쟁 실행을 원자적으로 재확인한다. 같은 키·다른 내용은 충돌하고 동시 동일 create는 job 하나/동일 응답만 남겨야 한다.

방지 시험: T-74/82/83 및 기존 T-100, runtime의 `test_t100_create_*`와 `test_t100_concurrent_duplicate_create_persists_one_job_command_and_initial_trigger` 신규9개(재시작 후 cache1, collision4, invalid key3, concurrent one-job1) 및 최초 실패 기존 시험. `tests-create-final-20261106-001`은 신규4개 파일 전체317개 중314 PASS/3 플랫폼 SKIP/0 FAIL·ERROR, exit0, 23.09초이며 신규9개 모두 통과했다. 추가 독립 Sol High의 `review/cache-first-review.md`는 `cache-first-manifest.json` 기준 APPROVED이며 reviewer의 새9개 실행도9 PASS다. 최초 CI 로그는 `.local-reports/orchestration-20261106/ci-first-20261106-001/`에 Git 제외 보존한다. 수정 커밋은 `1899e034120447559fd8d87129b220936f797895`다. 재시험 CI `42072357947`은 최초 실패 기존 T-100을 포함한 Linux959 PASS/15 SKIP, Windows343 PASS/3 SKIP, Dashboard31·단독18 브라우저 PASS로 전체 SUCCESS다. 이 로컬·모의 범위는 VERIFIED이며 실제 CLI/운영 인수로 확대하지 않는다.

## 2026-11-06 O1~O4 독립 리뷰 결함 · REG-0050~0059

공통 상태: **VERIFIED — 로컬·모의 범위 / 독립 코드 검토 APPROVED / 최종 CI SUCCESS**. 초기6건과 RR1~4 총10건을 `review/final-review.md`가 `final-manifest.json` 기준으로 수정 확인했다. 최초 근거는 `.local-reports/orchestration-20261106/review/findings.md`(로컬 전용, Git 제외)의 CHANGES_REQUESTED다. R1/2/3/5는 reviewer의 임시 fixture 재현, R4/6은 호출 경로 검사다. 수정 커밋은 `4c060bc7cfc1c6f0402a49cbaf82ca3076bfbe2d`이며 최종 재시험은 `1899e034120447559fd8d87129b220936f797895`의 CI `42072357947` 및 로컬 `tests-create-final-20261106-001`이다. 기존 T-71~84를 보강하며 [현재 실행 기록](runs/20261106-orchestration-v2.md)에 실패·수정·재검토를 이어서 남긴다. 환경별 미실행을 제품 결함이나 VERIFIED로 바꾸지 않는다.

| 회귀 ID | 재현/영향 | 원인·수정 방향 | 방지 시험·현재 재시험 |
|---|---|---|---|
| REG-0050 (R1/P1) | 분석을 `needs_decision`, 후보 없음으로 접수하면 최초 계획 확인과 설계 claim 가능 | 추적성이 needs_decision을 완료로 취급. 대응 후보/보류 또는 해결·반영 근거 검사 | T-78/79, no-candidate·해결/반영 전후. 최종 CI/로컬 재시험 VERIFIED |
| REG-0051 (R2/P1) | code 성공+review의 blocking 후보를 접수해도 후보/보류 없이 build 진입 | primary code 보고만 후보 생성. 모든 유효 current 보고의 후보를 결과와 원자 저장 | T-79/80, review 후보·stale/replay. 최종 CI/로컬 재시험 VERIFIED |
| REG-0052 (R3/P1) | 실행 전 workspace가 달라도 비코드 보고가 옛 소스를 반환하면 성공 가능 | 코드 외 단계의 frozen-vs-actual 대조 누락. Git40/내용SHA256 구분과 대상별 실행 전후 검사 | T-77/78/83, build/integration/review stale source·고정 분석/산출물 예외. 최종 CI/로컬 재시험 VERIFIED |
| REG-0053 (R4/P1) | coordinate/question 중 worker 재시작 후 receipt가 없어 UNKNOWN lane 해제 불가 | legacy native/bridge 호출에 receipt 옵션 미전달. v1 wire 유지하며 영속 process receipt 수집 | T-72/81/82, 무해한 로컬 프로세스·재시작/종료 증명. 최종 Linux CI와 Windows 로컬 결과를 함께 대조해 VERIFIED |
| REG-0054 (R5/P1) | 실제 a.c 변경과 무관한 fake.diff의 자기 해시로 code/review 통과 가능 | 서버가 측정한 전후 diff 대신 작성자 선언 해시만 사용. canonical 실제 delta bytes/해시 대조 | T-77/78/83, unrelated/omitted/binary/add/delete/mode/link diff. 최종 CI/로컬 재시험 VERIFIED |
| REG-0055 (R6/P2) | 보고 상세를 닫아도 polling마다 전체 wire/근거 이력을 전송 | list가 full data 반환. bounded metadata page와 별도 상세 조회로 분리 | T-84, 큰 이력의 bytes/page bound·닫힌 UI 상세 미요청. 최종 CI/로컬 재시험 VERIFIED |

### 후속 재검토 발견 — REG-0056~0059

| 회귀 ID | 재현/영향 | 원인·수정 | 방지 시험·현재 상태 |
|---|---|---|---|
| REG-0056 (RR1/P1) | frozen v1 job에 명시 v2 결과를 반환해도 legacy 성공 처리하고 blocking 보고를 버림 | adapter 정규화와 engine module/integration/control 이전에 명시 version/message_type 검증. genuine unversioned v1과 integer1 호환 보존 | T-77/83, C/R `test_rr1_*`: 성공/실패·bool/미지원·필드 생략·무해한 wrapper. 코드 검토 APPROVED, 최종 CI/로컬 재시험 VERIFIED |
| REG-0057 (RR2/P1) | code 종료·부모 result 없음·review ALIVE 상태에서 reconcile가 writer lease 해제 | 부모 성공 envelope에만 의존한 nested review 검사 제거. 모든 allocated review의 종료 또는 서버 nonce/id에 묶인 positive NOT_LAUNCHED 증명 필요. launched receipt와 모순되면 UNKNOWN | T-82, W `test_rr2_*`: 부모 결과 없음·ALIVE/UNKNOWN/TERMINATED/PID 재사용·미호출 proof·terminal replay. 코드 검토 APPROVED, 최종 CI/로컬 재시험 VERIFIED |
| REG-0058 (RR3/P2) | APPLIED 결정으로 해제한 동일 candidate가 재보고되면 새 active hold 생성 | unchanged 질문/선택지/영향/소스의 현재 적용 근거 재사용. 실질 변경은 이력 보존하며 candidate/hold/trigger 재개 | T-79/80, R `test_rr3_repeated_candidate_reuses_current_resolution_or_reopens_material_change`. 코드 검토 APPROVED, 최종 CI/로컬 재시험 VERIFIED |
| REG-0059 (RR4/P2) | v2 OpenCode가 reviewer 전용인데 configured 여부만으로 implementer로 선택·호출 | frozen 버전/역할과 작성자별 필수 독립 리뷰 쌍을 freeze/선택/claim/dispatch/intake에서 검사. 쌍 부재는 CAPABILITY_UNSUPPORTED로 호출 전 거부. v1 선택 유지 | T-76/78/83, C/R/W `test_rr4_*` 역할 행렬. 코드 검토 APPROVED, 별도 `rr4-targeted-20261106-001` 56 PASS/exit0. 전체291의2 FAIL 이력 보존; 보완 후 로컬314 PASS/3 SKIP 및 최종 CI SUCCESS로 VERIFIED |

C/R/W의 전체 경로·명령·실패 이력은 [현재 실행 기록](runs/20261106-orchestration-v2.md)을 따른다. RR1~3은 `review/rereview-1.md`, RR4는 `review/rereview-2.md`에 보존한다(모두 로컬 Git 제외). 이전 재검토89 PASS는 이전 manifest의 선택 실행이며 최종 전체 시험을 대신하지 않는다. REG-0050~0059 수정은 `4c060bc7cfc1c6f0402a49cbaf82ca3076bfbe2d`에 포함됐다. 최종 소스 `1899e034120447559fd8d87129b220936f797895`의 CI `42072357947`에서 Linux959 PASS/15 SKIP, Windows343 PASS/3 SKIP, Dashboard31·단독18 브라우저 PASS를 확인하고 아래 시험 연결과 플랫폼 근거를 대조해 로컬·모의 범위 VERIFIED로 기록한다. T-82 terminal envelope의 동일 replay/다른 내용 덮어쓰기 거부 시험은 불변성 방지 근거로 연결하되, 관찰된 별도 결함 없이 새 REG를 만들지 않는다. Linux 그룹 종료 검증은 CI의 무해한 시험 프로세스 범위이며 외부 추론·실서비스 재접속·운영 인수로 확대하지 않는다.

2026-11-06 후속 검증: REG-0043~0047의 수정은 새 구조의 현재 트리에 보존됐으며 별도 새 Luna의 focused Python384 PASS/6 SKIP·합성66 PASS·단독18 PASS·live 1+1 PASS로 관련 Git/모듈 선택/입력값/배치 사례를 다시 확인했다. 해당 로컬 범위는 VERIFIED다. [현재 실행 기록](runs/20261105-gui-test-layout.md)에 파일 manifest와 명령·로그를 연결하며 아래 최초 FAIL·기능별 독립 검토·검증 사본 이력을 유지한다. 회사/장비 운영 baseline은 NONE이다.

## REG-0048 · 독립 builder에 Git 통합 시험 혼입

RQ-54/D-57의 새 Astra 독립 코드 리뷰에서 `apps/gui-test/build.ps1`의 기본 시험 선택이 `test_integration_patch_contains_dashboard_import_dependencies`를 포함함을 발견했다(P2). 이 시험은 통합 patch를 만들기 위해 Git·Dashboard를 필요로 하므로 세 경로만 반입한 무Git 독립 빌드 계약과 충돌한다. 실패한 환경 fixture를 제품 결함으로 바꾼 기록이 아니라 실제 builder 선택 로직의 소스 finding이다.

단독 builder의 `-k` 조건에서 그 시험 하나만 제외했고 `backend/gui_test/tests/test_package.py`의 원래 시험과 전체 저장소 pytest 선택은 보존했다. 방지 검증은 T-164의 선택/패키지 경계와 T-166의 실제 Dashboard/Git 없는 독립 Windows 빌드다. 새 Astra 최종 재검토 APPROVED, 현재 focused Python 회귀 384 PASS/6 SKIP이며 새 Luna가 실제 Git 없는 자식 PATH·Node22.12.0/CPython3.12.10의 기본 독립 builder에서134 PASS/4 deselected·전체 wheelhouse·설치 Mock demo5를 확인했다. [20261105-gui-test-layout](runs/20261105-gui-test-layout.md)의 `final-acceptance-20261106/export-build.log`·시험 XML·build-info가 재시험 근거다. 상태 VERIFIED, 수정 커밋은 이 변경을 처음 포함하는 커밋이다. 운영 baseline NONE 유지.

## REG-0049 · README 한국어 UTF-8 손상

RQ-54/D-57 개발 README의 독립 앱 `npm ci` 누락(P2)을 수정하던 중 한국어 본문 인코딩이 실제 손상됐다. 새 Astra의 focused 재검토에서 발견했다. 정상 UTF-8의 직전 wheel staging README를 기준으로 전체 바이트·줄바꿈을 복원하고 의도한 ASCII `npm ci --prefix apps/gui-test` 한 줄만 추가했다. 기본 PowerShell 인코딩에 의존한 재작성은 사용하지 않는다.

T-167 산출물 README 검증과 T-168 문서 회귀에서 예방·추적한다. `.local-reports/20261105-gui-test-layout/readme-encoding-repair-20261106/verification.json`은 복원 전 정상본/최종 해시·정상 한국어 제목·replacement 문자 0과 정확한 한 줄 변경을 기록한다. 최종 README SHA256은 `99bd53a0e86dd5c623114f9aa5d812cce19f9b648f59459554bcfb29ed567360`이며 새 Astra가 원본과 전체 문장을 직접 비교해 APPROVED했다. source ZIP과 최종 독립 패키지에 같은 승인 README가 보존됐고 무Git 기본 builder·설치 Mock demo 및 문서 검사가 통과해 소스·패키지 보존 범위 VERIFIED다. [실행 기록](runs/20261105-gui-test-layout.md)에 최종 산출물 해시와 근거를 연결한다. 손상본과 발견·수정 이력은 로컬에 보존한다. 수정 커밋은 이 변경을 처음 포함하는 커밋이고 운영 baseline NONE은 유지한다.

## REG-0047 · Test 현황 좌우 패널 상단 불일치

사용자 제보: 데스크톱에서 TC 목록 박스보다 결과 박스의 시작 위치가 낮았다. 오른쪽 `.gt-main` 안에만 Run 선택·설정 toolbar가 있어 그 높이만큼 오른쪽 박스가 내려간 것이 원인이다. 패널 숨김·Run 선택·설정을 `.gt-layout` 위 공통 행으로 옮겨 양쪽 콘텐츠가 같은 grid 행에서 시작하도록 수정한다. 고정 margin offset으로 맞추지 않는다. 기존 조작·접근성 연결과 모바일 세로 배치를 보존한다.

방지 시험 T-161/GUI-UI-08·18은 1440/1024px에서 양쪽 박스의 y 차이 1px 이하, 빈/완료 Run·설정·목록 숨김/복원, 375px 넘침을 확인한다. Terra Low 수정·Sol Medium 시험 추가·별도 Sol High 재검토 APPROVED이며 실제 재시험 상태는 `20261104-test-results-cleanup` [기록](runs/20261104-test-results-cleanup.md)을 따른다. 원본의 새 공유 UI 경로와 검증 사본의 수정 파일 해시 일치를 확인했다. 수정 커밋은 이 항목을 처음 포함하는 커밋이다.

## REG-0046 · 실행 환경 입력값 바인딩 누락

`20261104-test-results-cleanup` 최종 합성 브라우저 시험은 65 PASS/1 FAIL이었다. 모드 설정 영역을 삽입한 긴 JSX 변경 줄에서 실행 환경의 host/account/workspace/source_revision/old_base/vendor_tree/new_base 입력 7개의 `value={profile[key]}`가 누락됐다. `onChange`와 서버 저장은 정상이라 두 번의 저장 요청은 기대값과 일치했지만 새로고침 후 입력칸이 비었다. trace의 reload GET 응답에 저장된 최신 값이 있음을 확인하여 fixture 문제와 구분했다.

원래 controlled value를 복구하고 기존 `guidelines.spec.ts`의 delayed settings save 시험과 전체 합성 회귀를 같은 기준으로 다시 실행한다. 기대값을 완화하지 않는다. 독립 Sol 리뷰는 이 P1을 앞선 소스 검토에서 놓친 사실을 인정하고 CHANGES_REQUESTED로 정정한 뒤 수정 파일을 재검토한다. 수정 커밋은 이 항목을 처음 포함하는 커밋이며 최초 실패·재시험·최종 상태는 [실행 기록](runs/20261104-test-results-cleanup.md)을 따른다.

## REG-0044 · Git 원격 정보의 미지원 형식

RQ-52 단위 시험 작성 중 `ext::…` 형식이 SCP 원격 주소 정규식에 포함되는 소스 문제를 발견했다. 실행 실패가 아닌 정적 검토 발견이다. SCP 경로가 `:`로 시작하는 미지원 형식을 거부해 원격 값을 미확인으로 반환하며 임의 원격 명령은 실행하지 않는다. 방지 시험은 `gui_test/tests/test_git_info.py`의 unsupported remote 사례/T-162, 수정 커밋은 이 항목을 처음 포함하는 커밋이다. 검증 상태는 `20261104-test-results-cleanup` [실행 기록](runs/20261104-test-results-cleanup.md)을 따른다.

## REG-0045 · 모듈 자동 목록의 선택과 조회 복구

새 Sol 최종 독립 소스 리뷰에서 세 가지 P2 문제를 발견했다. (1) 자동 프로파일의 배정 전 `frozen=false` 후보가 선택되지 않은 채 잠겼다. (2) 일시적 409/네트워크 오류 후 같은 문맥은 재조회하지 않아 실행 불가 상태에 머물렀다. (3) 현재 카탈로그가 비어 있으면 이미 배정된 자동 시험의 서버 동결 목록도 조회하지 못했다. 실제 시험 FAIL이 아닌 소스 리뷰 발견이다.

유효한 자동 소유 후보는 배정 전에도 선택된 읽기 전용 목록으로 표시한다. 실패 GET에만 250/750ms 간격의 최대 두 번 재시도와 소진 후 명시적 재확인을 제공하고, 정상 조회의 관련 없는 버전 갱신은 추가 조회하지 않는다. 자동 소유 기록이 있으면 현재 카탈로그가 비어 있어도 서버의 동결 기준을 읽는다. 일반 실행 차단·오래된 응답 거부·같은 문맥의 수동 선택 보존을 유지한다. T-163의 `workflow_diagram/tests/module-selection.spec.ts`에서 각각 재현·검증하며 수정 커밋은 이 항목을 처음 포함하는 커밋이다. 최종 검증 상태는 `20261104-test-results-cleanup` [실행 기록](runs/20261104-test-results-cleanup.md)을 따른다.

## REG-0043 · TC 헤더 토글 크기와 세션 보조 글씨

D-54/RQ-39 화면 정리의 독립 Sol 소스 리뷰에서 헤더로 옮긴 토글이 24px로 줄어 기존 GUI-UI-06의 28px 클릭 영역 조건과 충돌하고, `.gt-session-info` 부모의 12px만으로는 내부 `small`의 실제 글자 크기가 10~11px가 되는 문제를 발견했다. 최초 발견은 자동 시험 FAIL이 아닌 소스 검토다. 토글 28px와 이름 정렬 최소 32px를 보존하도록 좁은 패널의 헤더 grid 간격을 조정하고, 세션 대상·Mock 설명에만 12px를 명시했다. 비용 상세의 기존 11px는 유지한다. 방지 시험은 GUI-UI-06/14/18, T-152/T-161이며 자식 `small`의 실제 글자 크기도 확인한다. 수정 커밋은 이 항목을 처음 포함하는 커밋, 재시험 실행 ID는 `20261104-test-results-cleanup`이다. 현재 검증 상태는 [실행 기록](runs/20261104-test-results-cleanup.md)을 따른다.

첫 단독 GUI 실행은 17 PASS/1 FAIL로 GUI-UI-14의 최소 패널 너비에서 이름 정렬 버튼의 글자·화살표가 내부 너비를 넘었다. 최소 버튼 폭만으로는 정렬 표시의 실제 폭을 보장하지 못한 것이 원인이다. 이름 정렬의 `scrollWidth <= clientWidth + 1` 조건은 유지하고 헤더 너비 배분을 보완한 뒤 같은 시험을 재실행한다. 최초 실패 로그와 최종 결과는 위 실행 기록에서 구분한다.

## REG-0041 · UI 키보드·입력 보호 및 실행 확인

재현: 모달의 수동 focus 목록에 닫힌 details/비활성 입력이 포함됨; 설정 파일 가져오기는 숨긴 input의 label만 제공; 잘못된 JSON을 입력한 뒤 폼 제출을 우회하는 환경 점검 버튼을 누르면 이전 값을 저장; TC 순서 변경은 드래그만 가능; 테스트 중단은 확인 없이 즉시 요청됨. 원인과 수정 계약은 [UI 점검 명세](../design/WEB_GUIDELINES_AUDIT.md)에 기록한다. 방지 시험 T-153~155, 수정 커밋은 이 항목을 처음 포함하는 커밋이다. 재시험 실행 ID `20261104-web-guidelines-audit`; 검증 상태와 초기 실패는 [실행 기록](runs/20261104-web-guidelines-audit.md)을 따른다.

## REG-0039 · TC 트리 아이콘 크기가 설정 버튼에 전파

RQ-39 후속 구현의 독립 Sol High 리뷰에서 `.gt-tree-actions button`의 28px 규칙이 Test cases뿐 아니라 설정의 ‘설정 모두 접기/펼치기’ 텍스트 버튼에도 적용됨을 발견했다. 같은 클래스의 재사용을 확인하지 않은 것이 원인이다. CaseTree에만 `gt-tree-icon-actions`를 추가해 크기 규칙을 한정하고 기존 설정 버튼 크기를 보존했다. 방지 시험은 `tests/e2e/gui-test.spec.ts`의 트리 아이콘/설정 버튼 내용 잘림 검증이다. 수정 커밋은 이 항목을 처음 포함하는 커밋이며 재시험·독립 최종 검토는 [실행 기록](runs/20261104-hallmark-overview.md)을 따른다. 실제 장비 시험과 구분한다.

## 2026-11-03 병합 브라우저 회귀

- REG-0015: GUI-UI-03에서 worker 전이와 제어권/일시정지 클릭이 겹치면 서버가 VERSION_CONFLICT로 거부한다. 시험은 유효한 재시도 없이 PAUSED만 기다려 실패했다. 서버 정책은 유지하고 정확한 409/VERSION_CONFLICT에만 GET snapshot 후 동일 UI 조작을 최대 3회 재시도하도록 시험을 수정했다. RQ-11/RQ-38, `tests/e2e/gui-test.spec.ts` control/GUI-UI-03. 최초/두 번째 실패와 재시험은 [20261103-merge](runs/20261103-merge.md), 수정 기준은 해당 source manifest와 병합 커밋이다. 실제 제품 동시성 결함으로 확대하지 않으며 재시험 결과는 증거 JSON으로 확인한다.

  최종 VERIFIED: 수정 커밋 `d551492`, [20261103-merge-ci](runs/20261103-merge-ci.md)의 통합 브라우저18/단독13 PASS. 기존 실패 기록과 서버 버전 게이트를 보존했다.

확인된 로컬 결함과 수정은 아래 이력으로 관리한다. 실제 연동 미검증 위험을 발생한 버그로 작성하지 않는다.

| 필드 | 필수 내용 |
|---|---|
| regression_id | REG-0001부터 증가, 재사용 금지 |
| 증상·재현 | 입력·상태·동작·실제/기대 결과 |
| 영향 | RQ ID, 모듈/경로, 사용자 영향 |
| 최초 실패 | run_id, 코드/시험 revision, 증거 |
| 원인 | 확인 근거 또는 아직 미확인임을 명시 |
| 수정 | 수정 revision, 변경 요지, 대안/주의 |
| 방지 시험 | 기존/신규 T ID, 자동화 경로 |
| 재시험 | 새 run_id, PASS/FAIL, 증거 |
| 상태 | OPEN / FIXED_PENDING_VERIFICATION / VERIFIED / REOPENED |
| 정상 기준 | 검증 후 갱신한 baseline ID 또는 미반영 사유 |

같은 증상이 다시 발생하면 기존 REG를 REOPENED로 만들고 새 실패 실행을 연결한다. 이전 수정 기록을 지우지 않는다. 근본 원인이 다르면 새 REG를 생성하고 관련성을 연결한다.

## 2026-10-12 검증된 수정 기록

공통 수정 기준은 [구현 검증 기록](runs/20261012-implementation.md)의 code_revision/파일 manifest다. 새 코드가 커밋되기 전의 내용 해시로 시험 대상과 결과를 연결한다. 운영 baseline은 미등록이다.

| ID | 재현 / 원인 | 수정 / 방지 시험 | 최초 실패 → 재시험 | 상태 |
|---|---|---|---|---|
| REG-0001 | 첫 UI 빌드에서 nullable 객체 타입 검사 실패 | 명시적 null 보호 / TypeScript 빌드 | initial-build-failed → build PASS | VERIFIED |
| REG-0002 | 수동시험 select label 탐색이 선택지 텍스트와 충돌 | aria-label 명시 / T-59 UI | initial-browser-01-failed → 현재 browser PASS | VERIFIED |
| REG-0003 | 다른 모듈 상태 갱신 중 재시도 요청의 job version 충돌 | 동일 attempt/계획 명령에 한해 최신 버전 재접수, 서버 게이트 유지 / T-59, T-66 | initial-browser-02-failed → initial-browser-passed 및 현재 PASS | VERIFIED |
| REG-0004 | 시험 API bind 실패 후 기존 서버의 health를 성공으로 수용 | 사전 포트 확인, 새 runtime/키, 자식 프로세스 상태 확인 / 전체 UI runner | browser-failed 3 FAIL → 격리 재시험 3 PASS | VERIFIED |

RQ-14/15 입력 간소화와 RQ-28 데모 예외는 사용자 정책 변경이며 기존 필수 입력 계약을 버그로 기록하지 않는다. 새 정책의 방지 시험은 T-61~67이다.

## 후속 로컬 진입 검증

| ID | 재현 / 원인 | 수정 / 방지 시험 | 최초 실패 → 재시험 | 상태 |
|---|---|---|---|---|
| REG-0005 | 제거된 로그인 POST 경로를 무조건 404로 예상했으나 UI static mount가 있으면 405. 시험 기대값 오류 | T-68에서 정적 UI 유무에 따른 404/405 및 쿠키 미발급 확인. 다른 출처 차단 검증 유지 | backend-01: 86 PASS/1 FAIL → backend-02: 87 PASS | VERIFIED |

이번 수정 기준/실행별 결과/원문 출력은 [키 없는 진입 검증](runs/20261012-local-entry-agent-contract.md)에 있다. 첫 실패 당시 시험과 최종 수정 시험은 구분한다. D-38 접속 키 제거는 사용자 정책 변경이며 그 자체를 결함으로 기록하지 않는다. REG-0004의 시험 서버 식별은 새 runtime/키 방식에서 새 runtime/instance_id 대조로 갱신했고 UI 3개 PASS를 확인했다. 실제 운영 baseline은 미등록이다.

## 오케스트레이터 문서 확장

2026-10-12 D-39는 신규 설계이며 제품 코드 변경/결함 수정이 아니다. REG-0001~0005와 최초 FAIL·재시험 기록을 그대로 보존한다. T-71~85는 향후 회귀/인수 목록으로 추가했으며 아직 NOT_RUN이다. 실제 구현에서 결함이 재현되면 별도 REG와 실행 증거를 연결한다.

## 2026-10-12 M0 추가 확인

[Claude 패키지 실행](runs/20261012-claude-agent-package.md)에서 새 수동 계약의 ID/해시/권한/오래된 기준/UNKNOWN/덮어쓰기 거부 시험을 추가했다. 이 변경의 시험에서 발견되지 않은 결함을 새 REG로 만들지 않는다. 기존 REG-0001~0005와 최초 실패 기록은 그대로 유지하고 기존 기능 회귀를 함께 확인한다.

소스 기준/브리지 편의 변경은 T-92~95와 [20261012 실행](runs/20261012-settings-defaults.md)에 연결한다. 입력 편의 변경이 기존 job 기준이나 사용자 지정 명령을 바꾸지 않는 회귀 시험을 추가했다. 이번 시험 FAIL은 없고 기존 결함 이력은 유지한다.


## D-42 내장 연결 회귀

| ID | 재현 / 원인 | 수정 / 방지 시험 | 최초 실패 → 재시험 | 상태 |
|---|---|---|---|---|
| REG-0006 | 새 select/textarea의 중첩 텍스트가 정확한 label 탐색에 포함됨. 이전 REG-0002와 같은 유형이 새 필드에서 발생 | 명시 aria-label, 저장/재접속 T-101 및 고급 모드 T-95 | browser-initial/second → browser 최종 기록 | VERIFIED |
| REG-0007 | 브리지 추천 API 응답 중 workspace 편집 시 이전 workspace 기본 경로가 늦게 적용됨 | 응답 반영 때 현재 workspace로 기본값 정렬, 사용자 배열/현재 모드 보존 / T-95 | browser-second → browser 최종 기록 | VERIFIED |
| REG-0008 | 종료된 전경 프로세스의 회수한 PGID에 다시 killpg 호출, macOS 경계에서 PermissionError | 정상 종료 후 신호 생략. 종료 권한 실패면 UNKNOWN·잠금 유지 / T-100 | backend-process-failed → Python 217 PASS | VERIFIED |

실행별 최초 FAIL과 재시험은 [내장 연결 실행 기록](runs/20261012-native-cli.md)에 보존한다. 운영 baseline은 NONE이며 실제 Linux 인수와 구분한다.

## 2026-10-25 GUI Test 신규 모듈

| ID | 재현 / 원인 | 수정 / 방지 시험 | 최초 실패 → 재시험 | 상태 |
|---|---|---|---|---|
| REG-0009 | 빈 연결 프로파일 JSON 저장에서 KeyError로 500 반환 | 필수 connection 검증 후 422 반환 / GUI API test_invalid_saved_document_is_validation_error | feature-initial 2 FAIL 중 1건 → feature-second 63 PASS | VERIFIED |
| REG-0010 | 신규 폴더 탐색 시험이 이름 정렬상 첫 TC를 Dual로 잘못 가정 | path로 대상 식별, 분류/중복/메타데이터 충돌 검증 유지 / test_discovery_conflict_duplicates_and_symlink | feature-initial 2 FAIL 중 1건 → feature-second 63 PASS | VERIFIED |

실행 증거는 [GUI Test 기록](runs/20261025-gui-test.md)에 연결한다. 기존 REG-0001~0008의 수정/실패 이력을 보존한다.

- REG-0011: GitHub Actions 최초 실행에서 `--only-binary=:all:`로 끝나는 YAML scalar가 파싱 오류를 일으켜 job 생성 전 실패(run 40146320582). 해당 `run`을 block scalar로 수정하고 YAML 구문을 검증했다. 제품 로컬 시험 PASS와 CI 시작 실패를 구분하며 재실행 결과를 PR에 기록한다.

## 2026-11-01 업데이트 환경 재시험

[실행 기록](runs/20261101-local-update.md): 최초 281 PASS/3 FAIL은 ReportLab 누락과 Git 2.15.1의 init -b 미지원이었다. 공식 패키지 설치 및 이미 설치된 Git 2.54 선택 후 동일 3개 시험과 전체 284개 시험이 통과했다. 제품 코드/시험 기대값 변경은 없으며 신규 제품 결함으로 등록하지 않는다. 서버 바인딩 차단과 설치 미완료는 별도 환경 제약으로 유지한다.

## 2026-11-01 TC 화면 후속

- REG-0012: 375px에서 확장된 결과 표가 카드/페이지 폭을 넘침. 내부 grid minmax(0,1fr)와 결과 표 전용 가로 스크롤로 수정. 수정 커밋: 로컬 미커밋(source manifest 참조). 방지: GUI-UI-06 좁은 화면 검사 및 직접 Chrome 375px 재검사. 실행 ID 20261101-tc-workspace. 전체 자동 E2E는 환경 권한으로 BLOCKED.
- 개발 중 TS null 검사 실패 및 Python DB 재열기 fixture 실패는 [이번 실행 기록](runs/20261101-tc-workspace.md)에 최초 실패와 재시험 결과를 보존한다.

- REG-0013: 설정 톱니바퀴를 다시 눌러도 이전 화면으로 복귀하지 않음(사용자 제보). 원인: onClick이 settings만 설정하고 닫기 동작 없음. 수정: 결과 탭 복귀 버튼·톱니바퀴 toggle·Esc 및 포커스 복원. 방지: GUI-UI-11. 재시험: 20261101-repeat-settings Chrome 직접 3경로 PASS, 전체 자동 UI BLOCKED. 수정 커밋: 로컬 미커밋, [소스 manifest](runs/20261101-repeat-settings-evidence/source-manifest.json).

## 2026-11-02 게시 CI 회귀

- REG-0014: [CI 41441069153](https://github.com/graycoral/bsp_os_upgrade_dashboard/actions/runs/41441069153), GUI-UI-05에서 04_pair를 맨 앞으로 끈 후 03_link 아래로 되돌리면 순서가 그대로여서 FAIL(나머지16 PASS). 행 중앙 텍스트/경계 좌표에 의존한 native drag 경로를 확인하고 명시적 draggable 손잡이와 텍스트 선택 방지를 추가했다. 시험은 같은 위/아래 이동·Preflight 무효화·완료 Run 불변 기대값을 유지하면서 손잡이와 행 내부 하단을 사용한다. 수정: PR #5 후속 커밋. 재시험: CI 후속 실행 대기, 최초 실패 증거는 위 Actions artifact에 보존.

REG-0014 후속: CI 41442024136도 동일 GUI-UI-05에서 실패(16 PASS/1 FAIL). 손잡이 변경만으로 해결되지 않았다. 두 번째 드래그를 실제 포인터의 시작 임계 이동→대상 내부 이동→하단 이동→release로 나누고 native 이벤트를 기록하여 원인을 구분한다. 기대 순서/완료 Run 불변 검사는 유지한다.

REG-0014 원인 확정: CI 41442490944 native 이벤트에서 dragstart(y=969), 원본 행 dragover만 있고 dragend(y=1011), drop 없음. viewport 높이1000 밖으로 놓는 시험 좌표 오류였다. 손잡이/텍스트 선택은 주원인이 아니었다. 대상 행을 scrollIntoViewIfNeeded로 전체 노출한 다음 bounding box를 읽고 하단이 viewport 안인지 검사한다. 실제 포인터 drag와 순서 기대값은 유지한다.

## 2026-11-03 Windows 실행기 독립 리뷰 회귀

공통 수정 기준: [source manifest](runs/20261103-windows-runner-evidence/source-manifest.json), 실행 ID `20261103-windows-runner`. 독립 Astra가 재검토하고 GPT-6-sol이 Python133/브라우저16 PASS를 보고했으며 주 작업자가 결과를 확인했다. 실제 환경 baseline은 갱신하지 않는다.

| ID | 원인·재현 | 수정 / 방지 시험 | 재시험·상태 |
|---|---|---|---|
| REG-0016 | 명령 snapshot 없는 과거 Run claim에서 KeyError | 기본 Mock template fallback / 기존 test_default_and_legacy_runs_keep_mock_template | 최초125 PASS/1 FAIL → sol133 PASS; VERIFIED |
| REG-0017 | Windows os.execv supervisor가 TC exit7을0으로 전달 | 격리 subprocess supervisor와 종료 코드 전파 / test_exit_code_and_invalid_bytes_cannot_become_pass | Astra 독립 exit0→7 재현 및 sol133 PASS; VERIFIED |
| REG-0018 | 로그 조회 뒤 종료 사이 추가 FAIL/overflow 누락 | 종료 후 pipe EOF와 마지막 근거 확인 / test_final_pipe_tail_and_overflow_cannot_be_lost | sol133 PASS; VERIFIED |
| REG-0019 | 실행 전 거부/claim 후 전송 전 장애가 영구 UNKNOWN | durable rejection/reconcile tombstone / test_rejected_source_is_recorded_as_not_started_not_unknown 및 test_claim_before_send_recovery_fences_delayed_start | sol133 PASS; VERIFIED |
| REG-0020 | raw 파일 및 첫 공백까지만 가리는 masking으로 비밀값 잔존 | bounded in-memory capture 및 완성 credential line masking / test_secrets_split_across_writes_never_persist_in_logs | Astra Bearer 독립 재검사 및 sol133 PASS; VERIFIED |

자세한 최초 결함·수정·실패 이력·검토 모델·환경 한계는 [실행 기록](runs/20261103-windows-runner.md)을 따른다. 수정 커밋은 최종 게시 기록에 추가한다.

REG-0016~0020 게시 완료: 수정 커밋 `0ad590d6080c13b3d9618baa18c4aa7b8751737f`, PR #6 main 머지 `a80371c35cee434429871ad8718f97d396710788`. 별도 GPT-6-sol 확인 CI350/21/16 및 Windows133·PS5.1/7 패키지 모두 PASS. 이전 최초 실패·검토 근거는 보존한다.

## 2026-11-03 간결한 TC 목록 헤더

- REG-0021: 전체 선택을 이름 옆으로 이동한 최초 diff에서 최소240px 패널의 이름 셀이32px만 남아 체크박스와 정렬 화살표가 유형 제목에 겹칠 수 있었다. Astra 정적 리뷰 CHANGES_REQUESTED로 발견. 이름 열 최소64px와 끝 열24~70px 가변 너비로 수정했다. 방지 시험 GUI-UI-14는 최소 너비에서 체크박스/이름/유형 분리와 이름 버튼32px 이상·화살표 잘림 없음을 검증한다. 재시험 ID `20261103-compact-catalog`: 별도 GPT-6-sol UI16 및 240/300/375px geometry PASS; Astra 재검토 APPROVED. VERIFIED. 수정 코드 기준은 [실행 기록과 source manifest](runs/20261103-compact-catalog.md)에 보존하며 이 항목을 추가한 커밋이 수정 커밋이다.

## 2026-11-03 확정 명령 실행 경계

- REG-0022: 새 Windows 기본 명령 python3를 Host는 받지만 Manager.preflight의 python-only 검사로 Dashboard 실행이 COMMAND_NOT_ALLOWED로 거부됨. Astra P1 정적 리뷰 CHANGES_REQUESTED로 발견. runner.validate_windows_command를 양쪽에서 공유하고 test_manager_confirmed_single_and_dual_commands_end_to_end를 추가했다. 최초 GUI148 PASS는 경계 시험 누락으로 이 결함을 검출하지 못했으며 이력을 보존한다. 재시험 ID 20261103-confirmed-commands-costs: GUI149 PASS, 코드 재리뷰 APPROVED. 수정 코드 기준/최종 검증은 [실행 기록](runs/20261103-confirmed-commands-costs.md)에 보존하며 해당 항목을 추가한 커밋이 수정 커밋이다.

REG-0022 VERIFIED: 수정 커밋 `ecc5fd5355f68393a5d553a2b680a5df9856f03d`, PR #7 main 머지 `0f71a1fe0988a4b84e16771337bc27c6306649cc`. 독립 GPT-6-sol 확인 Linux366/통합UI22/단독UI17·Windows149 및 PowerShell5.1/7 CI PASS. 최초 지적과 로컬 제한은 실행 기록에 보존한다.

## 2026-11-03 결과 분리 키보드 회귀

- REG-0023: Run 선택의 키 이벤트를 탭 이동과 분리하려던 guard를 잘못된 resize separator에 적용해 키보드 너비 조절이 막히고 실제 tablist는 세션 선택 방향키를 가로챘다. Astra 초기 CHANGES_REQUESTED로 발견. separator 핸들러를 복원하고 TC 작업 화면 tablist에만 non-tab guard를 적용했다. 방지 시험 GUI-UI-08/18. Astra 재리뷰 APPROVED, 별도 시험 결과는 [실행 기록](runs/20261103-result-layout.md)에 보존한다. 이 항목을 추가한 코드 커밋이 수정 커밋이다.

- REG-0024: 세션 정보를 접으면서 관찰 모드 표시까지 숨겨져 GUI-UI-03이 실패했고, 중단되지 않은 Run의 예약으로 GUI-UI-04가 연쇄 실패했다(초기16 PASS/2 FAIL). 제어 중/관찰 모드는 결과 요약에 상시 표시하고 Run ID/상세 정보 접기는 유지했다. 방지 시험은 기존 GUI-UI-03/04, 재시험은 독립 GPT-6-sol 새 runtime 전체 브라우저. [실행 기록](runs/20261103-result-layout.md).

- REG-0025: 최초 PR #8 head5d2f680의 Linux 통합 GUI-UI-18에서 picker/gear 중심 y 차이11.25px로 실패(22 PASS/1 FAIL). Dashboard 전역 label의 column 방향이 새 Run picker에 남음. 기존 .gt label의 margin 초기화가 있으므로 직접 원인은 방향 누락이다. picker에 row 방향과 margin 초기화를 명시했다. 방지 시험은 동일 GUI-UI-18의 데스크톱/모바일 정렬 기준3px로 유지하며 수정 head CI 재시험을 기록한다. [실행 기록](runs/20261103-result-layout.md).

REG-0023~0025 VERIFIED: UI 수정2ac99a2, 최종 CSS 수정/검증 head `037be8a6a70b469606e6d779d7933b9cc30ceab7`; PR #8 main 머지 `4858d8f0b7fbbcd0a8965963da20632974441e76`. 별도 GPT-6-sol 확인 Linux366/통합UI23/단독UI18·Windows149 및 PowerShell5.1/7 CI PASS. 최초 정적 지적·로컬16/2 실패·Linux22/1 실패는 실행 기록과 증거에 보존한다.

## 2026-11-03 자동 퓨징 종료 근거

- REG-0026: Astra P1 정적 리뷰. FlashService.run의 Capture 생성 실패/프로세스 조회 예외 뒤 stop 실패를 무시하여 미종료 자식이 있어도 DONE으로 기록할 수 있었다. 전체 프로세스 생명주기를 보호하고 종료 불명은 UNKNOWN/예약 유지로 수정했다. 방지 시험은 가짜 ProcessTree/Capture 오류 주입이다. 추가로 복사 중 커지는 이미지 용량 제한·Linux lease 소유권·진행 중 endpoint 변경을 검사한다. [실행 기록](runs/20261103-automatic-flash-test.md)에 독립 재시험·리뷰·수정 코드 기준을 기록한다. 현재 재검증 중.

- REG-0027: 주 작업자 검토에서 콘솔 read와 command buffer clear 사이 경합을 발견했다. 읽기/추가를 같은 lock으로 묶고 명령 전 OS 입력 큐와 수집 buffer를 초기화해 이전 프롬프트가 새 진입 성공으로 사용되지 않도록 수정했다. 가짜 serial 회귀로 검증하며 실제 콘솔 타이밍 인수는 별도다. [실행 기록](runs/20261103-automatic-flash-test.md).

- REG-0028: 새 device_test Attempt에 이전 stage.result가 남아 재시도 중 과거 사례 결과를 현재 결과처럼 표시할 수 있었다. claim 시 현재 result를 비우고 이전 Attempt의 result/automation은 보존한다. 독립 재시도·이력 회귀 시험으로 검증한다. 계획 확인 모달의 수동 전용 설명도 D-48 기본 수동/활성 자동 방식으로 갱신했다. [실행 기록](runs/20261103-automatic-flash-test.md).

REG-0026~0028 로컬 VERIFIED: 새 Astra 최종 APPROVED, 별도 GPT-6-sol 관련 Python163/화면1/두 빌드 PASS. 실제 파일 해시와 최초 실패/재시험은 위 실행 기록에 보존한다. 이 항목을 포함한 코드 커밋이 수정 기준이며 CI 결과는 별도 추가한다.

REG-0026~0028 최종 VERIFIED: 수정·검증 head `145ee9881a4dacbbfa6fb8aceb8bea559417eed3`, PR #9 main merge `c72c2dabc0018b306269bd7e96b2f0d88db57b1e`. 별도 GPT-6-sol 확인 Linux413/통합UI24/단독UI18·Windows175 및 PS5.1/7 독립 배포 모두 PASS. 실제 보드 인수는 별도다.

## 2026-11-03 설정 마법사 초기 리뷰 회귀

- REG-0029: 새 Astra 초기 CHANGES_REQUESTED. 기존 Bash start.sh를 메뉴에서 부르면 background worker의 SIGINT 무시/종료 대기 누락과 상속 BSP_PORT로 잘못된 연결이 가능했다. Windows 두 파일 순차 저장·CMD pause 후 코드 손실·준비 후 runner 사망 미감지·보드 이름 변경 후 stale 콘솔 serial 충돌·legacy Dual COM에 노드를 강제하는 문제도 같은 구현 단위에서 지적했다. 새 마법사가 Python으로 API/worker를 직접 감독하고 고정 포트·Windows 단일 JSON 원자 저장·wrapper 종료 코드·runner/SSH 동시 감독·선택 프로파일 stale 매핑 제거·실제 template 기반 노드 조건으로 수정했다. 기존 수동 start.sh 자체는 이번 변경 범위가 아니다.
- 재현/방지: `tests/test_setup_runtime.py`의 자식 실패/정상 종료·원자 쓰기 실패·wrapper·보드 rename·legacy template 시험(T-137~140). 새 Astra 최종 APPROVED. 수정 커밋은 이 항목을 처음 포함한 커밋이며 파일 SHA256·독립 시험·Linux CI 결과는 [실행 기록](runs/20261103-setup-wizard.md)에 보존한다. 실환경 T-141은 별도다.

REG-0029 VERIFIED: 수정/시험 head `96e3a0296e55dca67c5d7bfeaca0c5cf657ffb75`, PR #10 main merge `8831df0d30e45e78f5fe1b8831de284d89a85394`. 독립 Astra APPROVED, GPT-6-sol CI Linux459/Windows221·브라우저24+18·PowerShell5.1/7 배포 PASS. 실환경 인수는 별도다.


## REG-0030 · Windows 공유 폴더 진입 실패 분석 정정

회사 PC는 파일 조회와 CMD dir Z:가 가능하고 `py -3 -X utf8 .\setup_runtime.py`가 정상 실행된다고 사용자가 보고했다. 이전 작업 PC의 Z: 부재를 회사 PC의 단절로 단정하고 UNC 경로를 추정한 것은 잘못된 진단이었다. ee561f1~d0b187d의 반복 수정과 로컬45 PASS는 실제 회사 CMD 진입 문제를 검증하지 못했다. 최초 증상은 계속 미해결로 보존한다.

대응은 사용자가 성공한 경로를 따라 Windows 진입점을 절대 파일 경로 직접 호출로 축소하는 것이다. 드라이브 재연결/캐시 의존성을 제거하고 새로운 회귀는 실제 CMD/PowerShell에서 다른 cwd·공백 경로·인자·종료 코드·줄바꿈을 검증한다. 구체적인 CMD 환경 원인은 미확정, 새 wrapper의 회사 실환경 인수는 별도다. 수정 커밋은 이 항목을 처음 포함한 커밋이며 [실행 기록](runs/20261103-direct-windows-launch.md)에 독립 리뷰·재시험 근거를 남긴다.

## REG-0031 · 실제 보기 오프라인 중단 차단

새 Astra 최초 검토에서 live API가 모든 action 전에 identity 응답을 요구하여 단절 중 pause/cancel/제어권 의도를 기록할 수 없음을 발견했다. 재현: 연결 실패 adapter로 legacy cancel은200, live cancel은503. resume/recover에만 연결 검사를 적용하고 나머지는 기존 Manager 상태·제어권 검증으로 처리한다. 독립 재검토 APPROVED. 방지 시험은 gui_test/tests/test_live_view.py(T-142), 수정 커밋은 이 항목을 처음 포함한 커밋이며 [독립 시험 기록](runs/20261103-live-test-view.md)에 재시험 근거를 남긴다.

## REG-0032 · 보기 전환 후 Test 현황 이탈

독립 브라우저 시험 보고를 주 작업자가 검토하며 전체 재로드 후 대시보드 overview로 돌아가는 문제를 발견했다. 초기 시험은 매번 Test 현황을 수동 클릭해 재진입하여 이 동작을 가렸다. 통합 앱이 유효한 guiExecution URL에서 Test 현황으로 시작하도록 수정하고 전환/재로드 뒤 추가 탐색 없이 상태를 확인하도록 시험을 강화한다. T-143, 수정 커밋은 이 항목을 처음 포함한 커밋이며 [실행 기록](runs/20261103-live-test-view.md)에 재시험을 남긴다.

## REG-0033 · 다이어그램 자동 Test의 실제 Attempt 연결

RQ-50 구현 중 독립 Sol High P2 리뷰: 초기 adapter/fixture가 실제 계약에 없는 payload.attempt_id를 사용해 자동 퓨징/부팅/TC 문구를 표시하지 못했다. backend의 payload.id/baseline.attempt_id와 현재 Attempt를 대조하고 실제 payload 모양의 T-145 시험으로 방지한다. 수정/검증 기준과 결과는 [다이어그램 실행 기록](runs/20261103-workflow-diagram-implementation.md)에 남긴다. 실제 보드 인수는 포함하지 않는다.

## REG-0034 · 비활성 다이어그램의 반복 렌더

RQ-50 구현 중 독립 Sol High P2 리뷰: 모델만 동결한 wrapper에 observation 갱신이 통과하여 숨겨진 펼친 단계까지 polling마다 다시 렌더했다. 비활성 탭의 렌더 경계와 재진입 시 관찰 갱신을 보호하고 T-148 render 수/애니메이션 검사로 확인한다. 수정/검증 기준은 [다이어그램 실행 기록](runs/20261103-workflow-diagram-implementation.md)에 기록한다.

## REG-0035 · 다이어그램 진입의 추가 상태 조회

RQ-50 주 작업자/독립 리뷰에서 탭 진입 effect가 기존 주기 밖 refresh를 실행해 추가 조회 0 조건과 불일치함을 발견했다. 진입 시 확인 필요 상태로 전환한 후 기존 polling의 다음 snapshot으로 흐름을 재개한다. T-148은 동일 시간 창에서 탭 왕복 유무에 따른 정확한 요청 수를 비교한다. 수정/재시험 근거는 [다이어그램 실행 기록](runs/20261103-workflow-diagram-implementation.md)에 남긴다.

REG-0033~0035 로컬 VERIFIED: 독립 Sol High 재검토 APPROVED, Luna Low 전체 32 PASS. 자동 Test 실제 payload 시험, inactive 관찰 10회 동안 DiagramView 3→3, 7,200ms 탭 왕복/무왕복 조회 4=4를 확인했다. 수정 코드는 미커밋이며 실행 기록의 파일 SHA256/manifest가 현재 검증 기준이다. 실제 회사·ACON 인수는 별도다.

## REG-0036 · Windows 빌드 PowerShell 실행 정책 차단

사용자 로컬 build.cmd 실행이 build.ps1 로드 단계의 UnauthorizedAccess로 실패했다. 자식 PowerShell 호출에서 실행 정책 옵션이 누락된 것이 원인이다. 해당 프로세스에만 Bypass를 전달하며 영구 정책·그룹 정책을 변경하지 않는다. CI에서는 PowerShell 7 모듈 경로가 Windows PowerShell 기본 경로보다 앞섰고 Security 모듈 TypeData 중복 로드 오류가 나타났다. 선택된 모듈 파일 경로는 기록되지 않았다. 배치 `setlocal` 안에서 자식 `PSModulePath`를 비워 Windows PowerShell의 기본 모듈 탐색을 복원한다. Restricted 직접 호출 실패와 CMD 경유 성공, LF/CRLF·다른 cwd·공백 경로·인자·종료 코드·부모 정책 비영속·상속 모듈 경로 제거 시험(T-126)을 유지한다. 초기 Astra APPROVED와 별도 sol 신규4/회귀49 PASS·4 SKIP·양쪽 UI 빌드 PASS 이후의 CI 실패 및 후속 재시험은 [독립 검증 기록](runs/20261103-build-execution-policy.md)에 구분한다. 수정 기준은 고정 커밋으로 기록하며 이전 회사 공유 경로 REG-0030의 미확정 원인과 별개다.


## REG-0037 · 예약된 전체 맞춤이 수동 배율을 덮음

수정 고정 커밋: `8702037dff276c3dd930e851cf7649ccb6ec46db` (REG-0037/0038 공통).

재현: 초기 overview ResizeObserver의 RAF가 예약된 뒤 100%를 선택하면 배율이 85%로 돌아간다. 원인: 예약 시점의 모드만 확인하고 실행 시점의 manual 모드를 확인하지 않았다. RAF 실행 때 현재 mode를 재검사해 수정했다. browser.spec.ts의 100%→축소→확대·유지 검사로 방지한다. 수정 커밋은 이 항목을 처음 포함한 후속 UI 커밋이며 [20261104-workflow-diagram-zoom](runs/20261104-workflow-diagram-zoom.md)의 초기 6 PASS/2 FAIL 및 최종 36 PASS에 근거해 로컬 VERIFIED.

## REG-0038 · 집중 영역/전체 보기의 카메라 복원

재현: 집중 보기에서 창 크기를 바꾸면 viewport 비례 여백이 바뀌어 선택 영역이 화면 밖으로 이동할 수 있고, 100개 모듈 overview에서 scrollTop 500 이후 탭 왕복하면 observer 최초 알림이 복원 위치를 덮는다. 원인: focus resize 미처리와 최초 동일 크기 알림/실제 크기 변경 미구분. passive scroll 기록·탭 복귀 복원과 host/graph 크기 비교, 실제 resize 시 선택 영역 재맞춤으로 수정했다. 창 크기 왕복 중앙 좌표 및 overview 500px 스크롤 왕복/갱신 보존 시험을 추가했다. 독립 리뷰 CHANGES_REQUESTED→APPROVED, 최종 36 PASS로 로컬 VERIFIED. 수정 커밋은 이 항목을 처음 포함한 후속 UI 커밋이며 [실행 기록](runs/20261104-workflow-diagram-zoom.md)에 근거를 보존한다.

## REG-0040 · TC 트리 토글 시험 선택자 범위 오류

GUI 시험 최초 실행은 17 PASS/1 FAIL이었다. GUI-UI-06의 `.gt-tree-actions` 선택자가 CaseTree의 토글뿐 아니라 `TestPage.tsx`의 카탈로그 표시 버튼도 함께 찾아 단일 버튼 검사가 실패했다. 제품의 단일 토글 동작과는 별개의 시험 범위 오류다. CaseTree 전용 `.gt-tree-icon-actions`로 선택자를 좁히고 기존 검증을 모두 유지했다. 재현·수정 및 재시험 상태는 [실행 기록](runs/20261104-tree-toggle.md)에 보존한다. 수정 커밋은 이 항목을 처음 포함한 커밋이며 `20261104-tree-toggle-retest`에서 전체 18 PASS로 로컬 VERIFIED.

## REG-0042 · 포터블 EXE의 리디렉션 출력 인코딩

실제 ZIP smoke에서 기본 Wizard를 stdin/stdout 파이프로 실행하면 CP949가 메뉴의 em dash를 표현하지 못해 첫 화면에서 UnicodeEncodeError로 종료했다. 외부 PYTHONUTF8 설정만으로 frozen 인터프리터 출력 인코딩이 바뀐다고 가정한 것이 원인이다. 포터블 진입점의 기본/Runner 모드에서 stdout·stderr를 UTF-8과 backslashreplace로 명시 설정한다. 격리 helper의 TC 출력 스트림과 소스 실행 경로는 유지한다. 방지 시험은 tests/portable_runner_smoke.py의 실제 ZIP 기본 메뉴 실행이며 초기 6 PASS/1 FAIL 로그와 후속 재빌드·재시험을 [포터블 검증 기록](runs/20261104-portable-runner.md)에 보존한다. 수정 커밋은 이 항목을 처음 포함하는 코드 커밋으로 고정한다. 최종 실제 ZIP smoke 7 PASS와 독립 Sol High 수정 리뷰 APPROVED로 로컬 VERIFIED다. 회사 PC 인수는 별도다.

## REG-0065 · 누적 통합 patch의 불완전한 호스트 전달

소스 확인으로 `package.py --base`가 allowlist의 `git diff`만 묶어 미추적 신설 파일·호스트 의존성을 빠뜨리고 다른 기준의 누적 변경을 결합함을 확인했다. `--base` CLI/프로그램 호출을 collection/output 전에 거부하고 source-only target·host-reference·현재 파일 hash manifest로 대체한다. 방지 T-186/187, 수정 커밋은 `99d46dc55cdffad1dbfb8a7b1ba2a5a8a4ce9557`이며 [실행 기록](runs/20261106-portability.md)에 재시험을 기록한다. 구현 직후 NOT_RUN, 최종 로컬 VERIFIED다.

## REG-0066 · ZIP INSTALL의 저장소 밖 문서 링크

소스 확인으로 기존 INSTALL이 앱 README를 루트에 복사하여 `../../docs/...` 및 루트 README 링크가 ZIP 밖을 향함을 확인했다. generated INSTALL/RELEASE_SUMMARY/contract와 앱 README/VALIDATION의 bounded 문서로 대체해 ZIP 내부 링크를 제공한다. 역사적 전체 문서 graph는 복사하지 않는다. 방지 T-187, 수정 커밋은 `99d46dc55cdffad1dbfb8a7b1ba2a5a8a4ce9557`이며 [실행 기록](runs/20261106-portability.md)에 ZIP 링크/해시 재시험을 기록한다. 구현 직후 NOT_RUN, 최종 로컬 VERIFIED다.

## REG-0067 · Git 조회 실패를 일반 폴더로 오인

소스 진단에서 Git 실패를 일반 폴더 fallback으로 처리해 손상 worktree·권한/설정 오류·Git 미설치와 detached HEAD를 혼동할 수 있었다. explicit non-repository 진단·rc128 및 상위 .git/bare metadata 부재를 모두 확인한 경우만 plain folder를 허용한다. detached symbolic-ref rc1은 실제 HEAD commit 확인 후 수용하고 나머지 오류는 실패로 보존한다. 방지 T-185의 source 오류 회귀, 수정 커밋은 `99d46dc55cdffad1dbfb8a7b1ba2a5a8a4ce9557`이며 [실행 기록](runs/20261106-portability.md)에 독립 재시험을 기록한다. 구현 직후 NOT_RUN, 최종 로컬 VERIFIED다.

## REG-0068 · Git·폴더 소스 제외 경로의 불일치

소스 확인으로 폴더와 Git이 runtime/자격증명 등 제외 경로를 다르게 판단하거나 제외된 symlink 항목에서 먼저 실패할 수 있음을 확인했다. execution.source.excluded_source_path를 양쪽에 공유하고 Git entry type/link 검증 전에 적용한다. 기존 revision 알고리즘과 허용 소스 bytes 계약을 보존한다. 방지 T-185의 Git/폴더 제외 경계 회귀, 수정 커밋은 `99d46dc55cdffad1dbfb8a7b1ba2a5a8a4ce9557`이며 [실행 기록](runs/20261106-portability.md)에 재시험을 기록한다. 구현 직후 NOT_RUN, 최종 로컬 VERIFIED다.

REG-0066 후속 독립 리뷰 P2: ZIP 문서/manifest가 전체 `backend/gui_test/tests`를 안내했으나 test_live_view의 top-level backend.api import와 host API/source 사례·full-host 재패키징 시험은 source-only ZIP 밖의 호스트를 요구한다. 명시적 portable 파일 목록과 호스트 의존 사례 3개의 -k 제외를 공통 상수로 생성해 INSTALL/HOST_CONTRACT/manifest에 같은 명령을 기록한다. 제외는 반입 범위 구분이며 전체 저장소 회귀에서는 모두 실행한다. 시험의 assertion/기존 FAIL/PASS를 바꾸지 않는다. 실제 extracted-only 명령 재시험은 [현재 실행 기록](runs/20261106-portability.md)에 별도 담당자가 기록한다.

REG-0065~0068 로컬 VERIFIED: 위 각 항목의 NOT_RUN은 구현 직후의 과거 상태다. 독립 Sol High 재검토 APPROVED 및 별도 Luna Low 재시험 PASS. 최종 코드/시험 manifest와 초기 실패 및 재시험은 [실행 기록](runs/20261106-portability.md)에 보존한다. 회사 인수는 별도다.

## REG-0071 · TC 카탈로그가 공통5초 제한으로 실패하고 점검 단계가 보이지 않음

재현: 느린 Windows TC 공유 폴더를 기존 Runner로 조회한다. 인증·보드 조회는 성공해도 catalog가 공통 HTTP5초를 넘으면 웹 목록이 실패하고, 기존 메뉴4는 진행 출력 없이 대기하여 실패 단계를 구분하기 어렵다. 실제 회사 오류 원인은 별도 확인 대상이며 로컬 재현은 지연/timeout fake transport로 구성한다.

원인: Linux WindowsRemote와 소스 마법사 runner_get이 catalog에도 공통5초를 적용하고 메뉴4는 모든 조회 후에만 출력했다. 수정은 목록 전용 기본100초·1~600초 영속 설정, 각 요청 시작의 유효값 캡처, timeout 오류 구분, 실패 중에도 가능한 웹 설정 및 호출 전 단계별 flush다. 연결·보드·제어5초와 TC 실행/lease·source version/Run을 보존한다. 방지 시험 T-191~193은 로컬 PASS, 실제 회사 인수 T-194는 NOT_RUN이다.

수정 커밋은 `7cad856f65798e3891e200d60e1301057161e3b8`이며 검증 후 동일 코드·시험을 고정했다. 재시험 실행 ID `20261106-catalog-timeout`, 상태 **LOCAL VERIFIED**. [실행 기록](runs/20261106-catalog-timeout.md), [이식 PORT-005](../porting/PORT-005.md). 승인된 기존 EXE 메뉴4는 이전5초 동작이며 이번에 교체하지 않는다.

## REG-0069 · 호스트 전역 heading 스타일의 UI 누출

portable/module 최초 시험은 14 PASS/3 FAIL이었다. 이 중 2건은 호스트의 전역 heading CSS가 스며들어 1024/1440 viewport에서 버튼 Y 위치가 7.5px 어긋난 동일성 실패다. scoped 상속 font와 native heading scale로 수정했다. 방지 시험은 `portable-ui.spec.ts`의 T-189이며 `browser-rerun-20261106-113246-533` 17 PASS, `workflow-rerun-20261106-113619-758` 74 PASS로 재시험했다. 수정 커밋은 `99d46dc55cdffad1dbfb8a7b1ba2a5a8a4ce9557`이며 당시 기준 manifest와 최초 실패는 [실행 기록](runs/20261106-portability.md)에 보존한다. 세 번째 실패는 별도 SSR 시험 harness 문제다.

## REG-0072 · 반복 포트 입력과 진단 경로 혼동

재현: 포트가 겹치는 회사 환경에서 매 실행 옵션을 다시 입력하고 Windows 로컬 및 Linux 역방향 경로를 구분해 진단한다. 포트 영속 저장과 명시적 단계 진단·래퍼로 개선한다. T-195~197 로컬 PASS 및 독립 리뷰 APPROVED, T-198 새 ZIP smoke 10 PASS, T-199 회사 인수 NOT_RUN. 수정 커밋 `792d862645a7113f86f2932b112c5222b7c4a64f`, 최초 실패와 재시험은 [실행 기록](runs/20261106-setup-commands.md)에 보존한다.

## REG-0075 · 플러그인 배치 결과·복구·제어 경계

독립 리뷰 재현에서 마지막 콘솔 drain에 도착한 panic·관찰 공백이 논리 결과에 반영되지 않고, 안전 준비 취소·인증 불가능한 제어 이전·플래시 프로파일 변경·UNKNOWN 복구·최종 예약 해제 확인에 결함이 확인되었다. 원인은 종료 증거와 상태 전이·권한·고정 프로파일 경계의 누락이다. 수정 후 panic·공백을 모든 결과에 반영하고 안전 취소와 인증 가능한 제어 이전, 프로파일 고정, UNKNOWN→READY 복구 및 RELEASE 확인 전 FINALIZING을 적용했다. runner_id 지적은 철회되었다.

방지 시험은 T-201·204~207 로컬 모의 시험이며 재시험 ID `20261107-bsp-upgrade-integration`이다. 수정 커밋은 `1a18ea6fab8b1caead3935ce70cb1e30153d631b`이고 실제 장비 인수는 NOT_RUN이다. 최초 재현과 리뷰 근거는 [실행 기록](runs/20261107-bsp-upgrade-integration.md)에 보존한다.
