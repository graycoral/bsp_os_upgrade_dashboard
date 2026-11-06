# 테스트 계획과 결과 관리

2026-11-04 D-54/RQ-20/39 후속: T-161과 기존 T-112/117/125/152를 GUI-UI-06/14/18 및 전체 탭 fixture로 검증한다. 제목 아래 소개 제거, 이름 헤더의 ＋/− 인접 배치, 진행률 아래 실행 조작, 작은 상시 세션 정보·결과·로그를 확인한다. 이전 하단 실행 카드·결과 접힘 기대값은 새 사용자 요구로 대체하며 Preflight·중단 확인·설정/비용 접기·Run 보존·375px 회귀는 유지한다. 실제 BSP/장비는 실행하지 않는다. [실행 기록](runs/20261104-test-results-cleanup.md).

2026-11-05 후속 T-161은 중복 결과 버튼/제목 제거·작은 진행률과 상태별 개수·환경 설정의 모드 적용·미준비 연결 안내 접기까지 포함한다. T-162는 `gui_test/tests/test_git_info.py`의 로컬 임시 Git·실패 모의와 UI 상태 표시, T-163은 모듈 선택기의 정확한 매칭/의존·서버 문맥/게이트/자동 소유 검증과 UI 자동 적용·오래된 응답 거부를 검사한다. 기존 일반 Run 요청과 스냅샷 해시 호환도 재검증하며 실제 Git 네트워크·모델·장비는 실행하지 않는다.

Windows 웹 빌드 T-126 후속: `tests/test_build_entrypoint.py`에서 실제 CMD/PowerShell을 사용해 Restricted 상속 정책의 차단 재현·수정 성공과 영구 정책 비변경을 검사한다. LF/CRLF·공백 경로·인자·성공/실패 종료와 기존 setup 진입점 회귀를 포함한다. 회사 그룹 정책/공유 폴더 인수는 별도다.

제품 시험과 문서 검사를 구분한다. 제품 자동 시험 러너가 추가되었다. [시험 목록](TEST_CATALOG.md)은 목표 인수 조건이고 자동 시험이 해당 조건 전체를 확인한 경우에만 최신 요약을 PASS로 갱신한다. 부분 검증과 실제 연동 미실행은 실행 기록에 따로 남긴다. 과거 화면 시안의 모의 검사 결과를 제품 PASS로 옮기지 않는다.

## 시험 수준

| 수준 | 검증 범위 | 증명하지 않는 것 |
|---|---|---|
| unit | 게이트·상태·진행률·정책·유효성 | 실제 외부 도구 연결 |
| contract | 결과 schema, API, fake adapter | 실제 CLI/Jira 동작 |
| integration | DB/worker/API/파일 및 오류 주입 | 실제 장비 통과 |
| ui/e2e | 실제 화면 조작과 백엔드 연결, fixture 표시 | fixture를 사용했다면 live 연동 |
| live | 지정 Linux/도구/Jira 환경에서 실제 호출 | 다른 환경/버전에서의 동작 |
| hardware-manual | 지정 보드/이미지/시험 계획의 사람 시험 | 다른 이미지/보드 결과 |
| documentation | 문서 링크·ID·상태표 일치 | 제품 구현 품질 |

목록의 각 시험은 필요한 수준에서 개별 실행을 기록한다. mock과 live를 같은 run_id로 덮어쓰지 않는다. 환경이 없어 못 돌린 항목은 BLOCKED 또는 NOT_RUN이며, 통과로 간주하지 않는다.

## 결과 정의

- NOT_RUN: 미실행. 초기 상태.
- PASS: 정의된 기대 결과를 해당 기준에서 실제 확인, 증거 존재.
- FAIL: 실제 실행 결과가 기대와 불일치. 재현 조건·원인/미확인·회귀 ID 기록.
- BLOCKED: 필요한 환경·권한·의존 결과가 없어 실행 불가. 이유와 해소 조건 기록.
- SKIPPED: 명시적 범위 제외와 승인 근거가 있을 때만 사용. 필수 시험을 임의 생략하지 않는다.
- INVALIDATED: 과거 PASS가 현재 입력/코드에 더 이상 유효하지 않음. 원래 실행 결과는 보존.

## 실행 기록

[TEST_RESULTS.csv](TEST_RESULTS.csv)는 현재 목표 기준의 최신 요약이다. [runs](runs/README.md)에 실행별 불변 기록을 먼저 남기고 요약을 갱신한다. 필수 필드: test_id, status, run_id, code_revision, test_revision, environment, executed_at, executor, evidence, defect_id, notes. PASS/FAIL에는 실제 실행 ID·revision·증거가 필요하다.

FAIL → 수정 → PASS는 두 개 이상의 실행 기록이다. 이전 FAIL 행을 실행 이력에서 수정/삭제하지 않는다. 변경으로 PASS가 무효화되면 요약에 INVALIDATED와 이유를 적고 다음 실행을 추가한다. 결과 기록 커밋은 실행 대상 코드 커밋과 다를 수 있으므로 둘을 구분한다.

## 단계별 종료·릴리스 조건

해당 단계 필수 시험과 영향 회귀 시험 통과, 미해결 차단 결함 없음, 문서·시험 목록 동기화가 필요하다. 전체 인수는 필수 live/hardware 범위도 충족해야 한다. 실제 연동이 없으면 “오프라인 구현 검증 완료”처럼 범위를 한정한다.

버그 수정은 재현 가능한 방지 시험을 추가한다. 단순 텍스트·배치 수정에 구현을 그대로 따라 쓰는 불필요한 시험은 만들지 않는다. 상태/복구/동시성/결과 유효성은 오류 주입 시험을 우선한다.

## 자동화 도입 지시

P1에서 도메인/저장 시험 러너와 정확한 실행 명령을 기록한다. P2에서 프로세스 중단·이벤트 역순·중복 요청 fixture를 추가한다. P3에서 UI 접근성·재연결 E2E를 연결한다. P7에서 CI가 필수 회귀 시험 실패 시 변경을 통과시키지 않도록 설정한다. 현재 Python 시험, UI 빌드, Playwright 시험 명령은 루트 README에 있으며 운영 CI는 아직 없다. 설치/실행 환경이 없는 live/hardware 항목은 계속 미실행으로 남긴다.

## 오케스트레이터·보고 v2의 단계별 검증

RQ-30~34와 T-71~85를 추가한다. O1 계약/필드 → O2 저장·중복·영향 보류 → O3 호출·장애·한도 → O4 UI → O5 실제 외부 wrapper 순으로 검증한다. 모델 출력은 fixture로 성공/실패/허위 완료/오래된 기준/중복 제안을 재현하며 실제 모델 호출 성공과 분리한다.

필수 회귀는 기존 분석 예외·계획/선행 게이트·공유 수정/빌드 잠금·교차 리뷰·수동 PASS/FAIL·데모 예외·Jira 중복 방지·키 없는 로컬 진입이다. 새 스키마/DB 이전은 기존 v1 job·FAIL 이력·명령 결과·artifact를 보존하는 복원 시험을 포함한다. 오케스트레이터 실패를 모듈 실패로 바꾸거나 독립 결과를 버리는지 집중 확인한다.

이전 D-39 요청은 문서 작업이었다. 링크/ID/JSON 예시·역할/계약 정합성만 검사하고 신규 제품 시험 15개는 NOT_RUN으로 유지한다. 이전 Python 87개/UI 3개 PASS는 해당 코드 해시의 기록이며 새 계약 구현의 통과 근거가 아니다.

## 수동 Claude 패키지 시험

RQ-35 / T-86~90은 실제 agent 파일 구조·권한 목록, 입력/응답/근거 검사, 실패/오래된 기준/재시도 미리보기, 독립 폴더 배포와 기존 파일 보존을 Python으로 검증한다. 기존 백엔드 시험·UI 빌드·격리된 데모 브라우저 회귀도 재실행한다. T-91 실제 Claude 검색/호출/판단 품질은 사용자가 수행하며 입력·응답·검사 결과·CLI/모델 버전과 시각을 보존한다. 자동 연동 T-71~85는 이 검사로 PASS가 되지 않는다.

소스/기본 브리지 변경은 RQ-36, T-92~95로 추적한다. 실제 Git 저장소는 시험용 임시 폴더에만 만들고 외부 agent/빌드는 호출하지 않는다. 기존 소스 유효성·명령 중복·게이트 회귀와 설정 화면 재접속을 함께 검증한다.


D-42/RQ-37/T-96~101은 임시 Linux CLI 모의 실행 파일과 로컬 Bash/파일, 별도 DB/runtime으로 검증한다. 실제 모델·BSP·Jira를 호출하지 않는다. 역할 지침 snapshot과 실행 토큰 제거·교차 리뷰·명령 산출물·환경 오류 분류·UNKNOWN 보류도 검사한다. T-102는 실제 Linux 계정에서만 수행할 인수 목록이며 모의 결과로 PASS 처리하지 않는다. 이전 브리지와 T-61~70/T-86~95 회귀를 함께 실행한다.

## GUI Test 회귀

RQ-38/T-103~107: `python -m pytest -q`는 기존 tests와 backend/gui_test/tests를 함께 실행한다. 공통 React 화면의 통합 회귀는 `python scripts/test_e2e.py`, 단독은 `python backend/gui_test/demo/browser_e2e.py`, 소스 headless Mock 시나리오는 `python -m backend.gui_test.demo.e2e --dashboard`다. 설치 wheel의 Mock 진입점은 기존 `python -m gui_test.demo.e2e`다. GitHub Actions에서 Linux 전체 회귀 및 Windows wheel 설치/독립 서비스 smoke를 분리한다. T-108 실제 회사 TC/RBM/보드 인수는 모의 통과와 구분한다.

## 2026-11-01 로컬 업데이트 검증

[로컬 main 업데이트](runs/20261101-local-update.md)에 Python 284개, 두 UI 빌드, 원 DB 백업/복원, 파일 해시와 환경 차단을 기록했다. E2E는 서비스 포트 8766과 겹치지 않도록 BSP_E2E_PORT=18766을 사용한다. 현재 CSV는 전체 인수 조건을 재확인하지 못한 이전 PASS를 INVALIDATED로 표시하며 이전 값은 실행별 기록에 보존한다.

## 현재 GUI Test 후속 범위

RQ-39~43 / T-109~118. 반복 plan·같은 slot 복구·이전 FAIL 보존·Suite/잘못된 입력·미집계/중복 usage·실제 대상 pin 검증을 core/API에서 먼저 확인한다. UI는 설정 복귀/입력 보존, 작은 트리·헤더 정렬, 목록 드래그/Preflight, 반복/Retry/진행률을 단독·통합 공통 회귀로 확인한다. 실제 BCM·모델 계량·장비는 별도 인수이며 fixture/Mock 통과로 대체하지 않는다. 최신 게시 증거는 [실행 기록](runs/20261102-publication.md)이다.

## Windows GUI Test 전용 빌드

RQ-44/T-119~121: `.github/workflows/gui-test-windows-build.yml`은 Windows PowerShell 5.1/7 각각에서 RQ-54의 세 경로 독립 묶음을 공백 포함 임시 경로로 복사해 빌드하고 새 환경에 오프라인 설치한다. Dashboard·Git 없는 독립 빌드와 CLI/health/정적 JS/Mock E2E를 확인한다. 패키지 경계는 `backend/gui_test/tests/test_package.py`, 기존 Dashboard 회귀는 기존 워크플로에서 실행한다. 실장비 인수 T-108과 별개다.

RQ-45/T-122~124: `backend/gui_test/tests/test_commands.py`로 치환·저장·snapshot·기존 Mock 호환을 검증하고 공통 GUI 브라우저 시험으로 저장/미리보기/실행을 확인한다. Windows 독립 빌드에도 명령 계약 시험을 포함한다.

## D-47 독립 검토·시험

구현 리뷰는 사용자 지정의 새 Astra 세션, 시험은 별도 GPT-6-sol 세션에서 수행한다. 시험 세션은 제품 코드를 수정하지 않고 명령·기준 해시·결과·실패 근거를 보고한다. 주 작업자가 원인/결과를 검토하고 수정 후 재시험을 요청한다. T-125~129는 mock/fixture/임시 프로세스 범위, T-130은 사용자 실환경 인수다.

## 자동 퓨징·TC 검증

RQ-47/T-131~135: 별도 GPT-6-sol 세션에서 가짜 콘솔·fastboot·배치, 임시 이미지/TC/DB로 상태 순서·해시·중복·단절·재시작·게이트·결과 계약과 수동 회귀를 검증한다. 새로운 Astra 세션은 구현만 리뷰하고 주 작업자가 실패를 수정·재시험 지시한다. 실제 COM/fastboot/BSP 작업을 실행하지 않는다. T-136은 사용자 실제 환경 인수로 별도 NOT_RUN이다. [실행 기록](runs/20261103-automatic-flash-test.md).


## RQ-49 실제 연결 보기

T-142~143은 임시 DB와 가짜 실행기로 연결 상태·새 실행 차단·오프라인 중단 의도·화면 전환을 검증한다. 두 UI 빌드와 기존 GUI 회귀를 수행한다. 회사 공유 경로/SSH/보드 인수 T-130/T-141은 별도다.

## RQ-50 다이어그램 탭

T-144~148은 `node workflow_diagram/tests/run.cjs`로 fixture 기반 구조·상태 변환·연결 단절·작업 전환·진행률·모션/접근성·회사 이식 경계와 기존 탭 회귀를 검증한다. `npm.cmd run build --prefix apps/web`와 `npm.cmd run build:gui-test --prefix apps/web`로 기존 두 빌드를 확인한다. T-149는 회사/ACON 실제 연결 인수이며 모의 응답으로 대체하지 않는다. [설계](../design/WORKFLOW_DIAGRAM.md), [실제 실행·환경 제약](runs/20261103-workflow-diagram-implementation.md)을 따른다. 과거 문서 검사와 제품 검증은 구분한다.

후속 [문서 리뷰](runs/20261103-workflow-diagram-review.md)로 같은 T-144~149의 인수 조건을 보완했다. 특히 current_stage와 RUNNING 차이, 취소 중/유효성/자동 Test, 연결 점과 실행 표시, 같은 version 관찰·늦은 실패·A→B→A, 그룹 간 게이트와 병렬 분석을 검사한다. 원본 앱 없는 격리 호스트의 production 빌드/표시와 실제 앱의 API mock 회귀를 구분한다. 효율성은 100개 모듈·80자 이름·375px/데스크톱에서 접힘/모두 펼침/반복 갱신을 측정하고 추가 네트워크 조회 0·비활성 렌더/모션 정지·접힌 단계 DOM 미생성을 확인한다. 착수 시 고정한 로컬 예산은 최초 표시/모두 펼침 각각 1,500ms, adapter 100ms이며 장비/bytes/parse/실측은 실행 기록에 남긴다. 동일 7,200ms 구간에서 탭 왕복 유무와 무관하게 기존 polling 요청 수가 같은지도 검사한다.

2026-11-04 후속 UI: T-144의 모듈 오른쪽 5단계 좌표/동일 행 배치, T-147의 RUNNING 진입 화살촉 transform 변화·수동 정지·stale 정지, T-148의 확장 후 그룹 겹침과 100개/375px 회귀를 검증한다. [후속 실행 기록](runs/20261104-workflow-diagram-rightward.md)을 따른다.

2026-11-04 배율/집중 후속: T-144/147은 수동 배율 유지, 선택 행 중앙 구도, 모션 줄이기와 창 크기 왕복, T-148은 전체 보기와 집중 보기의 탭 왕복/스크롤 보존·추가 조회 0을 검사한다. [실행 기록](runs/20261104-workflow-diagram-zoom.md).


전체 탭 모션 T-151은 기존 다이어그램 러너의 `motion.spec.ts`에서 합성 응답으로 검증한다. 일반/키보드/모션 줄이기, 모달 실제 진입과 즉시 닫기, GUI 내부 탭과 전체 6개 탭, 다이어그램 카메라·일시정지를 포함한다. [점검표와 실행 기록](runs/20261104-ui-motion.md).

## GUI Test 소스·앱 구조 · RQ-54/D-57

T-164~168은 이동 전 manifest·기존 미커밋 파일 보존, Python/UI import 경계, 두 UI 빌드, Dashboard/Git 없는 세 경로 반입, 소스 launch와 설치 wheel의 namespace/CLI·정적 자산, 기존 runtime/API/Mock 회귀를 검사한다. `apps/gui-test/build.ps1`과 `package.py --stage-wheel`을 사용하고 PowerShell 5.1/7·공백 경로·저장소 밖 설치를 구분한다. 기존 RQ-52/53/D-54 시험도 함께 확인한다. [구조 계약](../design/GUI_TEST_LAYOUT.md), [실행·리뷰 기록](runs/20261105-gui-test-layout.md)에 실제 명령·코드 기준·결과·환경 제약을 남긴다. 별도 Sol Medium 시험 작성·Luna Low 실행 보고와 사용자 지정 새 Astra 최종 독립 리뷰를 거치며, 실제 회사/보드 인수는 별도로 유지한다.

## 공통 환경 설정·문맥별 편집 · RQ-55/D-59

2026-11-06 설정 전용 화면 정정: T-169/170/172는 환경 설정에 Test 설정 편집기만 표시되는 경계를 확인한다. 모두 펼친 전역 화면에서도 TC 목록·검색·선택·순서 미리보기·개별 반복 조작, splitter, Test 제목/배너, Run 선택·진행률·결과·실행 조작은 숨긴다. TC 선택·순서·개별 반복은 Test 현황에서 먼저 변경하고 전역 왕복 후 복귀해서 보존을 확인한다. 기존 Run과 선택한 리포트도 복귀 시 유지한다. mode/source/connection/command/전체 반복/Suite 편집은 전역에서 가능하고, 동일 명령 textarea DOM과 양방향 draft 검증을 유지한다. 1440px와375px에서 설정 내용이 숨은 sidebar 공간 없이 전체 폭 한 열을 쓰며 가로 넘침이 없는지 확인한다. T-182의 전역 소스 적용 후 TC 선택 확인·조작도 Test 현황으로 돌아온 뒤 수행한다. 기존 전역 TC 조작 기대값을 올바른 화면 경계로 정정한 것이며 새 요구사항이나 실제 연동 범위를 추가하지 않는다. 이 정정의 실행 결과는 별도 실행 담당자의 근거가 나오기 전 NOT_RUN이다.

T-169~175는 `tests/e2e/settings-sync.spec.ts`에서 production 정적 빌드를 임시 포트로 제공하고 모든 API를 모의 응답으로 격리한다. BSP와 GUI 편집기의 전역/관련 탭 양방향 draft, 잘못된 JSON 원문·접힌 필드의 저장 차단/포커스, 명령 편집기 DOM 유지, TC 선택/반복, pending 보기 모드와 명시적 reload 적용, 개별/전체 접기·키보드·reload·375px, 저장 범위와 서버 version envelope, Preflight 무효화를 검증한다. T-170 추가 사례는 지연 capabilities 응답 도중 탐색과 초기화 중복 방지·가상 시계 기반 비활성 polling 중지/활성 재개를 확인한다. T-172 추가 사례는 접기 preference 읽기/쓰기 실패에도 조작·draft를 유지하고 전역/로컬 중복 DOM ID가 없음을 확인한다. 전체 browser storage 차단은 기존 세션 저장의 별도 범위이며 이 사례는 접기 preference 장애를 격리한다. 미실행은 NOT_RUN이며 작성 자체를 PASS로 기록하지 않는다. 별도 실행 담당자가 두 UI 빌드, 신규 시험과 기존 Dashboard/GUI/단독 화면 회귀를 실행하고 [실행 기록](runs/20261106-settings-sync.md)에 근거를 남긴다. 실제 소스 등록·저장소 파생 branch와 실제 외부 모델·장비·Jira 인수는 이 fixture 시험의 검증 범위에 포함하지 않는다.

## TC 소스 등록·고정 전달 · RQ-56/D-60

T-176~179는 `backend/gui_test/tests/test_sources.py`, `test_source_snapshots.py`, `test_source_transport.py`에서 임시 폴더·실제 local Git 저장소·별도 SQLite/Host runtime을 사용한다. 원격 Git 경계는 local Git 객체로 대체하고 실제 remote/보드 호출은 하지 않는다. 폴더/committed tree·하위 경로, 보조 파일 binary bytes, HEAD/index 보존, source 세대·version CAS·실패/restart/Legacy 복귀, stale Suite·Preflight와 Run 고정 문맥, source ZIP 검증·크기/경로 경계, old Runner capability·upload ack·legacy hash 호환을 확인한다. 무해한 Python 수행은 가짜 COM mapping 인자를 소비하고 snapshot 보조 파일만 읽으며, 실제 장비 시험이나 회사 GitHub/Gerrit 인증 인수로 해석하지 않는다.

T-180~182는 `tests/e2e/source-settings.spec.ts`에서 정적 production UI를 임시 포트에 제공하고 모든 API를 격리한다. 공유 source editor DOM/draft·실제 refs·Legacy 복귀, 늦은 inspect 결과 거부, 적용 실패 보존/입력 잠금, 새 catalog 명시 선택·반복/Preflight/Suite 무효화와 command draft 유지, disconnected live catalog 표시·실행 차단을 확인한다. 기존 T-169~175 fixture도 GET source 상태를 제공한다. 별도 실행 담당자가 Python 시험·두 UI 빌드·신규/기존 브라우저 회귀를 실행하고 결과를 기록한다. 이 절은 시험 의도이며 실행 전 결과는 NOT_RUN이다. 실제 원격 인증·SSH tunnel·회사 source 크기 성능·실장비 인수는 별도다.
