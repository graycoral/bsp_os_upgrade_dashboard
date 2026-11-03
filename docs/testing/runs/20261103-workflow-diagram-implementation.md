# RQ-50 다이어그램 탭 구현·검증

후속 코드 기준 고정: 사용자 커밋·푸시 승인에 따라 구현과 시험을 `199b04b5c080e41ec9794326828fbc4874cef633`에 커밋했다. 아래 미커밋/digest 표시는 시험 당시 기록으로 보존한다. 제품·시험 파일 내용은 동일하며 Git 줄바꿈 정규화만 raw hash와 구분한다. 이후 기준 기록 문서 변경 때문에 제품 시험을 재실행한 것으로 주장하지 않는다. PORT-001의 정식 원본 기준은 이 구현 커밋이다.

- run_id: `20261103-workflow-diagram-implementation`
- 상태: **IMPLEMENTED_LOCAL / MOCK_TESTED**. T-144~148 로컬 PASS, 회사/ACON T-149 NOT_RUN. 운영 인수 완료가 아니다.
- 승인: 문서 작성·별도 리뷰 후 사용자가 구현 착수를 명시했다.
- 기준 HEAD: `e86c5cbbf53cd360a1b90eafcc1c37b050e3659e` (`main`). 이 커밋은 구현 전 기준이다.
- 변경: `workflow_diagram/` 전용 표시/변환/조회 보호/시험, `apps/web` 연결, RQ-50 관련 문서. 작업 시작 시 존재한 문서 diff와 두 시안 디렉터리를 보존한다.
- 데이터/외부: DB·worker 실행 정책·설정 변경 없음. 실제 ACON/BSP/보드/Jira 실행은 범위 밖이다.
- 코드/시험 파일 기준: [source-manifest.json](20261103-workflow-diagram-evidence/source-manifest.json). 미커밋 변경의 `dirty_diff_hash`는 호스트 diff와 새 파일 해시 목록을 함께 포함한다. [호스트 접점 patch](20261103-workflow-diagram-evidence/host-integration.patch)는 기준 HEAD 대비이며 새 전용 폴더를 포함하는 전체 패치가 아니다. 별도로 변경된 scripts/build.cmd는 제외했다.

## 역할과 검증 기준

사용자 지정에 따라 구현은 GPT-6.1 Sol High, 단위 시험 작성은 별도 GPT-6.1 Sol Medium에 배정했다. 시험 실행·보고는 GPT-6 Luna Low, 독립 코드 리뷰는 구현 컨텍스트를 받지 않는 GPT-6.1 Sol High로 진행한다. 실제 완료 결과는 후속 절에 기록하며 배정만으로 검토/시험 완료를 선언하지 않는다.

착수 환경: Windows `10.0.26200`, Intel Core Ultra 7 258V / 8 logical CPUs / 32GB, Node `24.21.0`. 설치된 React/ReactDOM `19.3.0`, TypeScript `5.9.3`, Vite `7.3.7`, Playwright `1.64.0`을 확인했다. 실제 브라우저 버전은 시험 시 기록한다.

측정 전 고정한 로컬 성능 기준: 100개 모듈·80자 이름에서 최초 표시/모두 펼침 각각 1,500ms 이하, adapter 변환 100ms 이하. 빈 이력과 대표 누적 이력의 JSON bytes/parse 시간은 별도로 기록한다. 서버 전체 job JSON의 전송 비용을 adapter 최적화 성과로 계산하지 않는다. 접힌 단계 DOM 0, 다이어그램 자체 추가 fetch 0, 비활성·숨김·모션 정지 상태의 실행 애니메이션 0을 확인한다. 이 기준은 회사 환경의 성능 인수를 대신하지 않는다.

## 실행 결과

최종 실행: **32 PASS / 0 FAIL / 0 SKIP / exit 0**, 2026-11-03T14:42:18.602Z 시작, 46.043초. 별도 GPT-6 Luna Low가 Chrome `156.0.8078.80`으로 실행했고 주 작업자가 로그·검토 해시·화면 캡처를 대조했다. T-144~148 로컬 PASS, T-149 회사/ACON 인수 NOT_RUN, 운영 baseline NONE이다.

명령: `node workflow_diagram/tests/run.cjs` (`BSP_BROWSER_EXECUTABLE=C:/Program Files/Google/Chrome/Application/chrome.exe`). Vite/esbuild sandbox 접근 차단 후 승인된 동일 명령으로 재실행했다. 외부 서비스·실제 장비·운영 DB 대신 고정 fixture와 API route mock을 사용한다.

증거: [최종 전체 로그](20261103-workflow-diagram-evidence/full-retry.log.gz), [Playwright 결과](20261103-workflow-diagram-evidence/playwright-results.json.gz), [대시보드 빌드](20261103-workflow-diagram-evidence/build-dashboard.log.gz), [GUI Test 빌드](20261103-workflow-diagram-evidence/build-gui.log.gz), [최초 차단 로그](20261103-workflow-diagram-evidence/full-initial.log.gz), [증거 SHA256](20261103-workflow-diagram-evidence/evidence-manifest.json). [초기 단위 20 PASS 로그](20261103-workflow-diagram-evidence/unit-initial.log.gz)도 보존한다.

| 시험 | 최종 결과·실제 범위 |
|---|---|
| T-144 | PASS: 네 상위 노드 가로 배치·키보드/개별 펼침·같은 작업 탭 왕복 유지·작업 세대 전환 초기화·잘못된 소속 진단 |
| T-145 | PASS: 유효성·실제 RUNNING·code/build·취소/UNKNOWN·N/A·진행률 감소/미집계·실제 자동 Test payload 상관관계 |
| T-146 | PASS: 순수 수용 경계 및 실제 main.tsx route mock의 이벤트 단독 실패·timeout 복구·역순/작업 전환·명령 충돌 복구·새 작업 생성 |
| T-147 | PASS: 연결/실행 분리·선택적 흐름·병렬 분석 예외·키보드·모션 줄이기/정지·375px 및 100개 긴 이름·시각 확인 |
| T-148 | PASS: 전용 폴더 격리 production 빌드/표시·기존 두 빌드·앱 탭 회귀·CSS 격리·추가 조회 0·비활성 렌더/모션 0·아래 로컬 성능 기준 |
| T-149 | NOT_RUN: 실제 회사 프로젝트·ACON 제공자/매핑/만료·장비 연결 인수 |

제품 digest는 `2351aaff7c36ae304c186e17988611fd89c699f3b1e3960afbbc289468dbb6a9`, 시험 digest는 `a2bb6afadb65b9567dec2ea4a854e65e4b01b70b1dc1ee609d8dbdbe9251f9c9`다. `dirty_diff_hash=d9a85a3a4e35232b9f53b3e4912deb17309ff7e851c5aae39a104937f238c0ec`. 이 값은 manifest의 파일 목록 해시이며 Git 커밋이 아니다. 미커밋 파일과 빌드/시험 기준을 대조하는 용도다.

## 성능·시각 확인

고정 fixture는 100개 모듈, 이름 80자, 각 6단계다. 대표 이력은 단계마다 8 Attempt와 합성 로그/12개 TC 보고를 포함한다. 다음 수치는 회사 서버의 실측이 아니다.

| 측정 | 결과 |
|---|---|
| 대표 job JSON 크기 / 브라우저 JSON.parse | 7,046,307 bytes / 14.2ms. JS bundle 크기가 아님 |
| 100개 화면 표시 / 전체 펼침 | 39.6ms / 134.3ms. 각각 1,500ms 기준 충족 |
| adapter 20회 최대 | 1.6589ms. 100ms 기준 충족 |
| 추가 네트워크 | 격리 화면 요청 0; 7,200ms 동일 창에서 탭 왕복 4회의 기존 조회 4회 = 왕복 없는 조회 4회 |
| 비활성 상태 | 관찰 10회 갱신에서 실제 DiagramView 진입 횟수 3 → 3; 실행 중 애니메이션 0 |
| 접힘/펼침 DOM | 접힘 시 단계 목록 0, 100개 전체 펼침 시 단계 목록 100 |

누락된 빈 이력 비교를 같은 fixture/adapter의 Node 직접 import로 추가 측정했다(코드/시험 수정·브라우저 재실행 없음). [payload-metrics.json](20261103-workflow-diagram-evidence/payload-metrics.json)은 각 20회 측정이며 빈 이력 101,307 bytes의 parse 최대/중앙값 1.6778/0.2628ms, adapter 1.4212/0.2452ms; 대표 이력 7,046,307 bytes의 parse 14.9526/12.0612ms, adapter 0.8134/0.4709ms다. Node와 브라우저 측정은 서로 다른 실행이므로 수치를 합산하지 않는다.

React production 환경에서 외부 Profiler 값은 0/빈 배열이므로 이를 실제 렌더 0 또는 React CPU 시간으로 해석하지 않는다. 화면 표시/펼침 시간은 두 animation frame까지의 경과 시간이고 비활성 렌더는 별도 함수 진입 계측이다. 서버 네트워크 전송 시간은 측정하지 않았다.

주 작업자는 [데스크톱](20261103-workflow-diagram-evidence/desktop.png), [375px 화면](20261103-workflow-diagram-evidence/narrow.png)을 직접 확인했다. 실제 사용자 작업이 아닌 격리 fixture이며 좁은 화면은 가로 순서를 유지하고 캔버스를 좌우로 스크롤한다. 기존 앱 없는 격리 빌드와 실제 앱 route mock 통합을 모두 확인했다.

## 남은 범위

ACON 실제 제공 계약과 회사 UI/데이터 구조는 미확정이다. Python 실행 파일 누락으로 표준 문서 검사기와 Python 전체 백엔드 회귀는 이번 작업에서 실행하지 않았으며, 기존 PASS를 재사용해 통과로 주장하지 않는다. 백엔드/GUI Test/DB 소스는 변경하지 않았다. 문서 정합성은 동등 PowerShell 검사로 별도 확인한다. 회사 전달 전 코드 커밋 고정이 필요하며 미커밋 manifest를 커밋으로 오인하지 않는다.

최종 정합성: [동등 문서 검사](20261103-workflow-diagram-evidence/doc-validation.json) PASS, `git diff --check` PASS. 실제 시험 시 해시 23개와 전달 manifest 27개가 현재 파일과 일치하며 T-1~143의 기존 CSV 기록도 HEAD 대비 그대로다. 작업 도중 별도로 생긴 `.runtime-gui/`와 변경된 `scripts/build.cmd`는 이 기능의 소스/시험 범위에 넣거나 삭제하지 않았다. 기존 두 시안 디렉터리도 보존했다.

초기 환경 확인에서 `.venv/Scripts/python.exe -X utf8 docs/testing/validate_docs.py`는 누락된 Python 3.13 실행 파일 때문에 exit 103으로 실행되지 않았다(BLOCKED). 이 환경 문제를 제품 FAIL로 바꾸거나 Python을 임의 설치하지 않았다.

초기 단위 실행은 20 PASS / exit 0이다. 전체 브라우저 첫 실행은 Vite/esbuild의 상위 경로 접근 거부로 20 PASS / runner 6 FAIL / 6 미실행 / exit 1이었다. 여섯 실패는 화면 준비 단계에서 막혀 assertion이 실행되지 않았으므로 제품 결함 검증 결과와 구분한다. 최초 로그/해시는 `.local-reports/workflow-diagram/full-initial.*`에 보존한다. 최초 단위 해시 목록은 경로 오기로 adapter 해시가 누락돼 최종 전체 manifest로 보완한다.

두 빌드는 각각 sandbox의 같은 접근 제한 뒤 승인된 동일 명령 재실행에서 PASS(exit 0)했다. `tsc -b`도 통과했다. 명령은 `npm.cmd run build --prefix apps/web`, `npm.cmd run build:gui-test --prefix apps/web`이며 로그는 `.local-reports/workflow-diagram/build-dashboard.log` 및 `build-gui.log`에 최초 오류와 재실행을 함께 보존한다.

비활성 렌더 시험은 부모 Host의 commit까지 세는 외부 Profiler 횟수를 실제 컴포넌트 실행으로 오인하지 않도록 계측 경계를 수정했다. 임시 격리 복사본의 DiagramView 진입만 계측하고 원본 제품 파일은 수정하지 않는다. 실제 함수 진입 증가 0 조건은 유지하며 Profiler commit 수는 별도 측정한다.

## 독립 리뷰 중간 발견

- REG-0033 / P2 / T-145: 자동 Test 표시에서 초기 adapter가 존재하지 않는 `automation.payload.attempt_id`를 읽어 실제 자동 단계 설명을 누락했다. 실제 backend는 `payload.id` 및 `payload.baseline.attempt_id`로 현재 Attempt와 연결한다. 초기 시험 fixture도 잘못된 형태여서 실제 계약 형태로 수정한다. 검토는 정적 코드 대조이며 아직 시험 실행 실패를 주장하지 않는다.
- REG-0034 / P2 / T-148: 초기 비활성 탭 wrapper가 adapter 결과만 동결하고 observation은 전달하여 숨겨진 100개 모듈/500개 단계의 render가 polling마다 반복되는 경로를 발견했다. inactive 렌더 경계를 보호하고 실제 render 수로 재검증한다.
- T-144/146 초기 통합 경계: 새 작업 생성도 작업 선택의 동일 세대 전환 경로를 사용하도록 통일했다. 비활성 중 A→B→A 전환은 context generation으로 구분하고 일반 탭 왕복은 펼침 상태를 유지한다. 해당 브라우저 회귀를 추가했다.
- REG-0035 / P2 / T-148: 주 작업자와 독립 리뷰에서 다이어그램 진입마다 즉시 refresh를 호출해 기존 polling 밖 조회가 추가됨을 확인했다. 재진입은 확인 필요 상태만 설정하고 기존 polling의 다음 관찰을 기다리도록 수정한다. 초기 요청 수 시험은 클릭 후 카운트와 ±1 허용으로 이 차이를 놓칠 수 있어 같은 시간 창의 정확한 요청 수 비교로 보완한다.

위 항목은 구현 세션과 분리한 GPT-6.1 Sol High가 발견했다. 수정·재시험·최종 리뷰 판정 전에는 해결 완료로 표시하지 않는다.

## 제품 코드 독립 재검토

별도 GPT-6.1 Sol / High의 최종 정적 판정은 **APPROVED**다. 새 작업 생성의 세대 전환, 실제 자동 Test payload 상관관계, 비활성 memo/만료 타이머, context generation, 탭 진입 추가 조회 제거를 직접 재확인했다. 읽기 전용 코드 리뷰이며 시험 실행/회사 인수를 대신하지 않는다.

검토된 핵심 파일 SHA256:

| 파일 | SHA256 |
|---|---|
| apps/web/src/main.tsx | 166DA3320D1F83B9B2D9A4987E7FFABC7C1E3E48625971A719AA5B718F83D70E |
| apps/web/tsconfig.json | 04079BB657427591E1C9876A625C1AC5416504ACC01B125D7F346F2F642F3827 |
| workflow_diagram/web/DiagramTab.tsx | 12ECEF9A7FC3D2A65B96DF6F3171FBFD3C28B10202623BB4CF48C783C5338CA8 |
| workflow_diagram/adapters/dashboard.ts | E6DAFFBDC8A6FCCF80FD6BA6BE6FC1173013D0B678CBFF71F02FD02219BE20AB |
| workflow_diagram/host/snapshot.ts | 41CCBBAB1C6CB6DD0BEB0983538D1DC891535EA549C7F0EA9F7D807C676C0633 |
| workflow_diagram/web/presentation.ts | 1627AC1D09ABACC2639935F199DA56244D456CF8F98D13F858CDF0C308C0D3FF |
| workflow_diagram/web/types.ts | 620F93089F58359D72A0220C4E024CB349470A81EFB10B3716143A56E5DF14EB |
| workflow_diagram/web/diagram.css | BB1CFEC9B3715AABDB3A145036B075C16BED75F4B4232B9D02F65BD16FEA8813 |
| workflow_diagram/web/index.ts | 30CDE18CDE563D432B45DA3CC7F8ADABCCFF8EBDC6D7BBFAE8896C086C32FB91 |

추가된 요청 수 회귀는 고정 시계의 7,200ms 구간에서 탭 왕복/무왕복 각각 기존 4회 조회로 동일해야 한다. 구현 수정 후 테스트 작성은 완료했으나 실행 판정은 별도 아래 결과로 남긴다.
